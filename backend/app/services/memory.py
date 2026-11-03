import re
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
