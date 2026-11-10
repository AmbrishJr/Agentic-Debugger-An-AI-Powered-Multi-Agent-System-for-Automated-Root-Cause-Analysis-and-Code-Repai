"""Bounded Python AST metadata and deterministic dependency retrieval. Never imports code."""
import ast
from collections import OrderedDict, defaultdict
import copy
import re
import sys
import time
from threading import RLock
from app.services.security import digest, read_source, redact_source
from app.services.repository_snapshots import verify_snapshot, StaleSnapshotError
from app.services.validation_runs import protected_test_path

PARSER_VERSION = f'python-ast-v1-{sys.version_info.major}.{sys.version_info.minor}'
MAX_FILES = 200
MAX_REMOTE_FILES = 40
REMOTE_READ_SECONDS = 20
MAX_BYTES = 4 * 1024 * 1024
MAX_NODES = 200000
MAX_FILE_NODES = 20000
MAX_SYMBOLS = 5000
CACHE_SIZE = 8
_CACHE = OrderedDict()
_LOCK = RLock()
LIMITATIONS = 'Python static symbols/imports/direct calls only; dynamic dispatch, re-exports and other languages may be unresolved. Retrieval relationships are not proof of causality.'


def module_names(path):
    parts = path[:-3].split('/')
    if parts[-1] == '__init__':
        parts.pop()
    names = ['.'.join(parts)]
    if parts and parts[0] == 'src':
        names.append('.'.join(parts[1:]))
    return [n for n in names if n]


def scope_nodes(node):
    """A lexical scope's nodes, excluding bodies of nested definitions."""
    pending = list(reversed(node.body))
    while pending:
        current = pending.pop()
        yield current
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        pending.extend(reversed(list(ast.iter_child_nodes(current))))


def imported(node, module, package_file):
    if isinstance(node, ast.Import):
        return [(a.asname or a.name.split('.')[0], a.name if a.asname else a.name.split('.')[0]) for a in node.names]
    if isinstance(node, ast.ImportFrom):
        prefix = module.split('.') if package_file else module.split('.')[:-1]
        if node.level:
            if node.level > len(prefix):
                return []
            base = prefix[:len(prefix)-node.level+1]
            if node.module:
                base += node.module.split('.')
            target = '.'.join(base)
        else:
            target = node.module or ''
        return [(a.asname or a.name, '.'.join(filter(None, (target, a.name)))) for a in node.names if a.name != '*']
    return []


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + '.' + node.attr if base else None
    return None


def parse_file(path, content):
    tree = ast.parse(content, filename=path)
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_FILE_NODES:
        raise ValueError('node_limit')
    module = module_names(path)[0] if module_names(path) else ''
    package = path.endswith('/__init__.py') or path == '__init__.py'
    scopes = []
    def definitions(parent, prefix='', class_name=''):
        for node in scope_nodes(parent):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            name = '.'.join(filter(None, (prefix, node.name)))
            scopes.append((node, name, class_name))
            definitions(node, name, name if isinstance(node, ast.ClassDef) else class_name)
    definitions(tree)
    imports = [target for n in nodes for target in ([a.name for a in n.names] if isinstance(n, ast.Import) else [t for _, t in imported(n, module, package)])]
    module_aliases = {}
    for n in scope_nodes(tree):
        for alias, target in imported(n, module, package):
            module_aliases.setdefault(alias, set()).add(target)
    # A binding that is assigned/redefined is not a reliably resolved import.
    module_assignments = {n.id for n in scope_nodes(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    module_shadowed = set(module_assignments)
    module_shadowed |= {n.name for n in scope_nodes(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    symbols = []
    calls = []
    for node, name, class_name in scopes:
        identifier = f'{path}:{node.lineno}:{name}'
        kind = 'class' if isinstance(node, ast.ClassDef) else ('async_function' if isinstance(node, ast.AsyncFunctionDef) else 'function')
        symbols.append({'id': identifier, 'path': path, 'name': name, 'short_name': node.name,
                        'kind': kind, 'line_start': node.lineno, 'line_end': node.end_lineno})
        aliases = {key: set(values) for key, values in module_aliases.items() if key not in module_shadowed}
        local_imports = defaultdict(set)
        local_nodes = list(scope_nodes(node))
        for n in local_nodes:
            for alias, target in imported(n, module, package):
                local_imports[alias].add(target)
        aliases.update(local_imports)
        shadowed = {n.id for n in local_nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        shadowed |= {n.name for n in local_nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            shadowed |= {arg.arg for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]}
            shadowed |= {arg.arg for arg in (node.args.vararg, node.args.kwarg) if arg}
        for n in local_nodes:
            if not isinstance(n, ast.Call):
                continue
            target = dotted(n.func)
            if not target:
                continue
            parts = target.split('.')
            first = parts[0]
            if first in ('self', 'cls') and class_name and len(parts) == 2:
                calls.append((identifier, path, class_name + '.' + parts[1], None))
            elif first in shadowed:
                continue
            elif first in aliases and len(aliases[first]) == 1:
                target = next(iter(aliases[first])) + ('.' + '.'.join(parts[1:]) if len(parts) > 1 else '')
                calls.append((identifier, None, None, target))
            elif len(parts) == 1 and first not in module_assignments:
                calls.append((identifier, path, first, None))
    return {'symbols': symbols, 'imports': imports, 'calls': calls, 'nodes': len(nodes)}


def build_index(corpus):
    symbols, imports, calls, skipped = [], {}, [], []
    used = 0
    limited = False
    for path, content in sorted(corpus.items()):
        try:
            data = parse_file(path, content)
        except (SyntaxError, ValueError, RecursionError):
            skipped.append({'path': path, 'reason': 'unsupported_syntax_or_file_limit'})
            continue
        if used + data['nodes'] > MAX_NODES or len(symbols) + len(data['symbols']) > MAX_SYMBOLS:
            limited = True
            skipped.append({'path': path, 'reason': 'index_budget'})
            continue
        used += data['nodes']
        symbols.extend(data['symbols']); imports[path] = data['imports']; calls.extend(data['calls'])
    modules = defaultdict(set)
    for path in imports:
        for name in module_names(path): modules[name].add(path)
    definitions = defaultdict(list)
    for symbol in symbols:
        definitions[(symbol['path'], symbol['name'])].append(symbol['id'])
    def target(value):
        parts = value.split('.')
        for length in range(len(parts), 0, -1):
            paths = modules.get('.'.join(parts[:length]), set())
            if paths:
                if len(paths) != 1: return None
                path = next(iter(paths))
                return path, '.'.join(parts[length:])
        return None
    dependencies = set()
    for path, values in imports.items():
        for value in values:
            resolved = target(value)
            if resolved and resolved[0] != path: dependencies.add((path, resolved[0]))
    edges = set()
    for caller, path, name, value in calls:
        resolved = (path, name) if path else target(value)
        matches = definitions.get(resolved, []) if resolved else []
        if len(matches) == 1: edges.add((caller, matches[0]))
    return {'symbols': symbols, 'calls': sorted(edges), 'imports': sorted(dependencies),
            'indexed_files': len(imports), 'skipped': skipped, 'limited': limited, 'parser_version': PARSER_VERSION}


def index_for(source, snapshot, files):
    if snapshot.get('version') != 1:
        return None, False, ['Legacy source has no pinned manifest; using path-based retrieval.']
    kind = source.split('@')[0]
    key = (snapshot.get('repository_id'), snapshot.get('commit_sha'), snapshot.get('snapshot_id'), PARSER_VERSION)
    if kind in ('local', 'sample'):
        verify_snapshot(snapshot, kind)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None: _CACHE.move_to_end(key)
    paths = sorted(p for p in files if p.endswith('.py') and not protected_test_path(p))
    file_limit = MAX_REMOTE_FILES if kind == 'github' else MAX_FILES
    limited = len(paths) > file_limit
    paths = paths[:file_limit]
    corpus, total, notices = {}, 0, []
    tree = None
    if kind == 'github' and cached is not None:
        return copy.deepcopy(cached), True, []  # Immutable revision; source access was checked by list_files.
    if kind == 'github':
        from app.services import github_source
        tree = github_source.tree(source)
    started = time.monotonic()
    for path in paths:
        if kind == 'github' and time.monotonic() - started > REMOTE_READ_SECONDS:
            limited = True
            break
        if kind in ('local', 'sample'):
            try:
                raw = read_source(kind, path)
            except (ValueError, OSError):
                raise StaleSnapshotError('An indexed file is unavailable. Submit a new incident.') from None
            if digest(raw) != snapshot['files'].get(path):
                raise StaleSnapshotError('An indexed source file changed. Submit a new incident.')
        elif kind == 'github':
            raw = github_source.read_blob(tree.get(path, ''))
        else:
            return None, False, ['Unsupported source; using path-based retrieval.']
        total += len(raw.encode())
        if total > MAX_BYTES:
            limited = True
            break
        # Never retain strings/comments/secrets in the index; parse redacted text.
        corpus[path] = redact_source(raw)
    if kind in ('local', 'sample'):
        verify_snapshot(snapshot, kind)
    if cached is not None:
        return copy.deepcopy(cached), True, []
    value = build_index(corpus)
    value['limited'] = value['limited'] or limited
    with _LOCK:
        _CACHE[key] = copy.deepcopy(value)
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_SIZE: _CACHE.popitem(last=False)
    return value, False, notices


def stack_candidates(files, selected, frames, sample=False):
    paths = list(selected)
    for frame in frames:
        matches = [p for p in files if frame['path'] == p or frame['path'].endswith('/' + p)]
        if not matches:
            matches = [p for p in files if p.rsplit('/', 1)[-1] == frame['path'].rsplit('/', 1)[-1]]
        if len(matches) == 1: paths.append(matches[0])
    if sample and 'README.md' in files: paths.append('README.md')
    return list(dict.fromkeys(p for p in paths if p in files))


def rank_files(files, selected, frames, log, index, limit, sample=False):
    baseline = stack_candidates(files, selected, frames, sample)
    scored, reasons = {}, defaultdict(list)
    def add(path, score, reason):
        if path not in files or (protected_test_path(path) and path not in selected): return
        scored[path] = max(scored.get(path, 0), score)
        if reason not in reasons[path]: reasons[path].append(reason)
    for position, path in enumerate(selected): add(path, 1000-position, 'Explicitly selected for this investigation.')
    trace_paths = stack_candidates(files, [], frames)
    for path in trace_paths: add(path, 800, 'Unambiguous path in the submitted stack trace.')
    symbols = index['symbols'] if index else []
    by_id = {s['id']: s for s in symbols}
    by_name = defaultdict(list)
    for s in symbols: by_name[s['short_name']].append(s)
    words = set(re.findall(r'\b[A-Za-z_]\w*\b', log))
    anchored = set()
    for frame in frames:
        frame_paths = stack_candidates(files, [], [frame])
        for s in symbols:
            if s['path'] in frame_paths and s['line_start'] <= frame['line'] <= s['line_end']:
                anchored.add(s['id'])
    for name, matches in by_name.items():
        if name in words and len({s['path'] for s in matches}) == 1:
            for s in matches:
                add(s['path'], 500, 'A uniquely located symbol is named in the log: ' + name)
                anchored.add(s['id'])
    anchored.update(s['id'] for s in symbols if s['path'] in selected)
    # Trace functions (including callers) outrank broad file-import neighbors.
    frontier = set(anchored)
    seen = set(frontier)
    for depth in range(2):
        following = set()
        for caller, callee in index['calls'] if index else []:
            if callee in frontier:
                s, other = by_id[caller], by_id[callee]
                add(s['path'], 700-150*depth, f"Static caller of {other['name']} in {other['path']}.")
                following.add(caller)
            if caller in frontier:
                s, other = by_id[callee], by_id[caller]
                add(s['path'], 650-150*depth, f"Direct call from {other['name']} in {other['path']}.")
                following.add(callee)
        frontier = following - seen
        seen.update(following)
    seeds = set(scored)
    for importer, imported_path in index['imports'] if index else []:
        if importer in seeds: add(imported_path, 400, 'Imported by relevant source: ' + importer)
        if imported_path in seeds: add(importer, 350, 'Imports relevant source: ' + imported_path)
    if sample and 'README.md' in files: add('README.md', 300, 'Bundled behavior contract.')
    baseline_order = {path: position for position, path in enumerate(baseline)}
    ranked = sorted(scored, key=lambda path: (-scored[path], baseline_order.get(path, len(baseline)), path))[:limit]
    return ranked, dict(reasons), baseline[:limit]


def retrieve(source, snapshot, files, selected, frames, log, limit, strategy='symbols'):
    sample = source.split('@')[0] == 'sample'
    index, hit, notices = index_for(source, snapshot, files) if strategy == 'symbols' else (None, False, [])
    if strategy == 'stack' or index is None:
        ranked = stack_candidates(files, selected, frames, sample)[:limit]
        reasons = {p: ['Selected file, unambiguous stack path, or bundled behavior contract.'] for p in ranked}
    else:
        ranked, reasons, _ = rank_files(files, selected, frames, log, index, limit, sample)
    summary = {'strategy': strategy, 'parser_version': PARSER_VERSION if index else None,
               'cache_hit': hit, 'indexed_files': index['indexed_files'] if index else 0,
               'skipped': index['skipped'][:10] if index else [], 'skipped_count': len(index['skipped']) if index else 0,
               'index_limited': index['limited'] if index else False, 'notices': notices, 'limitations': LIMITATIONS}
    details = {}
    for position, path in enumerate(ranked):
        symbols = [s for s in index['symbols'] if s['path'] == path] if index else []
        details[path] = {'strategy': strategy, 'rank': position+1, 'reasons': reasons.get(path, []),
                         'symbols': [{k: s[k] for k in ('name', 'kind', 'line_start', 'line_end')} for s in symbols[:20]]}
    return ranked, details, summary
