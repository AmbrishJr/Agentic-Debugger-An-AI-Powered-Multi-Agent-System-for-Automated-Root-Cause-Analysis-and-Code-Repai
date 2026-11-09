"""Offline-first evaluation. No production database or integration mutations."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'benchmarks/v1')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/evaluations/latest')
    parser.add_argument('--mode', choices=['demo', 'live'], default='demo')
    parser.add_argument('--allow-live', action='store_true')
    parser.add_argument('--provider', choices=['openai', 'gemini'])
    parser.add_argument('--model')
    parser.add_argument('--max-cases', type=int)
    parser.add_argument('--split', choices=['development', 'held-out', 'all'], default='all')
    parser.add_argument('--authorize-isolated', action='store_true')
    parser.add_argument('--check-fixtures', action='store_true')
    parser.add_argument('--adjudications', type=Path)
    args = parser.parse_args()
    if args.mode == 'live' and not (args.allow_live and args.provider and args.model and args.max_cases):
        parser.error('Live evaluation requires --allow-live, --provider, --model and --max-cases. Costs may be incurred; cost instrumentation is unavailable.')
    if args.max_cases is not None and not 1 <= args.max_cases <= 50:
        parser.error('--max-cases must be between 1 and 50')
    if args.check_fixtures and not args.authorize_isolated:
        parser.error('--check-fixtures requires --authorize-isolated')
    args.max_cases = args.max_cases or 8
    with tempfile.TemporaryDirectory(prefix='autorca-evaluation-') as temp:
        scratch = Path(temp)
        os.environ.update(DATABASE_URL='sqlite:///' + str(scratch / 'evaluation.db'), AUTH_ENABLED='false',
            MIGRATE_ON_STARTUP='true', JOB_EXECUTION='inline', GITHUB_TOKEN='', GITHUB_REPOSITORY='',
            REPOSITORY_ROOT=str(scratch), AUTORCA_API_TOKEN='',
            SANDBOX_ENABLED='true' if args.authorize_isolated else 'false',
            LLM_PROVIDER=args.provider or 'openai', OPENAI_MODEL=args.model if args.provider == 'openai' else 'gpt-4.1-mini',
            GEMINI_MODEL=args.model if args.provider == 'gemini' else 'gemini-3.5-flash-lite')
        os.environ.pop('VERCEL', None)
        if args.mode == 'demo':
            os.environ.update(OPENAI_API_KEY='', GEMINI_API_KEY='')
        from app.evaluation.runner import run, markdown
        result = run(args, scratch)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n')
        args.output.with_suffix('.md').write_text(markdown(result))
        print(str(args.output.with_suffix('.md')))


if __name__ == '__main__':
    main()
