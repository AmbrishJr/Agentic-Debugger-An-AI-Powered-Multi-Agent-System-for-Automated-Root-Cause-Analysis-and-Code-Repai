import re
import math
from collections import Counter
from typing import Protocol
from sqlalchemy import text, select
from app.models.records import IncidentMemory, Incident, ProposedFix


class Retriever(Protocol):
    def search(self, query: str, exclude_id: str, limit: int = 5) -> list[dict]: ...


class FTSRetriever:
    def __init__(self, db):
        self.db = db

    def search(self, query: str, exclude_id: str, limit: int = 5) -> list[dict]:
        tokens = list(dict.fromkeys(re.findall(r'[a-zA-Z][a-zA-Z0-9_]{2,}', query)))[:16]
        if not tokens:
            return []
        expression = ' OR '.join('"' + t + '"' for t in tokens)
        rows = self.db.execute(text('''SELECT incident_id, error_signature, root_cause,
            resolution_summary, bm25(memory_fts) AS rank FROM memory_fts
            WHERE memory_fts MATCH :query AND incident_id != :id ORDER BY rank LIMIT :limit'''),
            {'query': expression, 'id': exclude_id, 'limit': limit}).mappings().all()
        return [dict(r, retrieval='SQLite FTS5 BM25 keyword match; not semantic similarity') for r in rows]


class HybridRetriever:
    """Local TF-IDF concept vectors plus BM25. No provider calls or model downloads."""
    concepts = {
        'timeout': ('timeout', 'timed', 'deadline', 'latency', 'slow', 'unresponsive'),
        'memory': ('memory', 'oom', 'allocation', 'heap'),
        'authentication': ('authentication', 'unauthorized', 'credential', 'credentials', 'login', 'signin'),
        'connection': ('connection', 'connect', 'network', 'socket', 'connectivity'),
        'database': ('database', 'sql', 'query', 'postgres', 'sqlite'),
        'division': ('division', 'divide', 'divisor', 'zerodivisionerror'),
        'missing': ('missing', 'absent', 'notfound', 'unavailable'),
    }

    def __init__(self, db):
        self.db = db

    @classmethod
    def tokens(cls, value):
        words = re.findall(r'[a-z][a-z0-9_]{2,}', value.lower())
        mapping = {word: concept for concept, words in cls.concepts.items() for word in words}
        return Counter(mapping.get(word, word) for word in words)

    def search(self, query, exclude_id, limit=5):
        records = self.db.scalars(select(IncidentMemory).join(Incident).where(IncidentMemory.incident_id != exclude_id)
                                  .order_by(Incident.created_at.desc()).limit(500)).all()
        if not records:
            return []
        docs = [self.tokens(r.error_signature + ' ' + r.root_cause + ' ' + r.resolution_summary) for r in records]
        q = self.tokens(query)
        frequencies = Counter(word for doc in docs for word in doc)
        idf = {word: math.log((1 + len(docs)) / (1 + count)) + 1 for word, count in frequencies.items()}
        def vector(tokens):
            values = {word: (1 + math.log(count)) * idf[word] for word, count in tokens.items() if word in idf}
            norm = math.sqrt(sum(v*v for v in values.values())) or 1
            return {word: value/norm for word, value in values.items()}
        query_vector = vector(q)
        scored = sorted([(sum(value*query_vector.get(word, 0) for word, value in vector(doc).items()), r)
                         for doc, r in zip(docs, records)], key=lambda pair: pair[0], reverse=True)
        ranks, candidates = {}, {}
        for rank, (score, r) in enumerate(scored):
            if score <= 0: continue
            ranks[r.incident_id] = 1/(60+rank+1)
            candidates[r.incident_id] = {'incident_id':r.incident_id, 'error_signature':r.error_signature,
                'root_cause':r.root_cause, 'resolution_summary':r.resolution_summary, 'vector_similarity':round(score, 4)}
        for rank, item in enumerate(FTSRetriever(self.db).search(query, exclude_id, limit*2)):
            identifier = item['incident_id']
            ranks[identifier] = ranks.get(identifier, 0) + 1/(60+rank+1)
            candidates.setdefault(identifier, item)
        return [{**candidates[identifier], 'rank':ranks[identifier],
                 'retrieval':'Hybrid BM25 and local TF-IDF concept vectors; curated vocabulary, no neural embeddings'}
                for identifier in sorted(ranks, key=ranks.get, reverse=True)[:limit]]


def remember(db, incident, analysis, triage):
    existing = db.scalar(select(IncidentMemory).where(IncidentMemory.incident_id == incident.id))
    if existing:
        return
    fix = db.scalar(select(ProposedFix).where(ProposedFix.incident_id == incident.id))
    resolution = 'Proposed only; no deployed resolution recorded.'
    if fix:
        resolution += ' ' + fix.explanation
    memory = IncidentMemory(incident_id=incident.id, error_signature=triage.get('exception', 'Unknown'),
        root_cause=analysis.get('summary', 'Incomplete investigation'), resolution_summary=resolution,
        retrieval_metadata={'mode': incident.mode, 'approval': 'pending', 'deployed': False})
    db.add(memory)
    db.flush()
    db.execute(text('INSERT INTO memory_fts(incident_id, error_signature, root_cause, resolution_summary) VALUES (:id, :signature, :root, :resolution)'),
               {'id': incident.id, 'signature': memory.error_signature, 'root': memory.root_cause, 'resolution': resolution})
