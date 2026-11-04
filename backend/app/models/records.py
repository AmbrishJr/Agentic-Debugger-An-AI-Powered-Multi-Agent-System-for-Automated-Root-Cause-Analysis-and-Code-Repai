import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, JSON, Float, Boolean, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid.uuid4())


class Incident(Base):
    __tablename__ = 'incidents'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(180))
    error_log: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String, default='medium', index=True)
    status: Mapped[str] = mapped_column(String, default='submitted', index=True)
    mode: Mapped[str] = mapped_column(String, default='demo')
    repository: Mapped[str] = mapped_column(String, default='sample')
    selected_files: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String, default=now, index=True)
    updated_at: Mapped[str] = mapped_column(String, default=now)
    resolution_note: Mapped[str] = mapped_column(Text, default='')
    resolution_evidence: Mapped[str] = mapped_column(Text, default='')
    resolved_at: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)


class Investigation(Base):
    __tablename__ = 'investigations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id'), unique=True)
    agent_status: Mapped[str] = mapped_column(String, default='queued')
    root_cause_summary: Mapped[str] = mapped_column(Text, default='')
    evidence_references: Mapped[list] = mapped_column(JSON, default=list)
    analysis_results: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class ProposedFix(Base):
    __tablename__ = 'proposed_fixes'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id'), unique=True)
    path: Mapped[str] = mapped_column(String)
    original_code: Mapped[str] = mapped_column(Text)
    proposed_code: Mapped[str] = mapped_column(Text)
    original_sha256: Mapped[str] = mapped_column(String)
    proposed_patch: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    risks: Mapped[list] = mapped_column(JSON, default=list)
    validation_result: Mapped[dict] = mapped_column(JSON, default=dict)
    approval_status: Mapped[str] = mapped_column(String, default='pending')
    decision_note: Mapped[str] = mapped_column(Text, default='')
    decided_at: Mapped[str | None] = mapped_column(String, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String, nullable=True)
    pr_status: Mapped[str] = mapped_column(String, default='none')
    files: Mapped[list] = mapped_column(JSON, default=list)


class AgentExecution(Base):
    __tablename__ = 'agent_executions'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey('investigations.id'), index=True)
    agent_name: Mapped[str] = mapped_column(String)
    execution_status: Mapped[str] = mapped_column(String, default='running')
    duration: Mapped[float] = mapped_column(Float, default=0)
    output_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=now)


class IncidentMemory(Base):
    __tablename__ = 'incident_memory'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id'), unique=True)
    error_signature: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str] = mapped_column(Text)
    resolution_summary: Mapped[str] = mapped_column(Text)
    retrieval_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class AppPreference(Base):
    __tablename__ = 'app_preferences'
    id: Mapped[str] = mapped_column(String, primary_key=True, default='default')
    values: Mapped[dict] = mapped_column(JSON, default=dict)


class ValidationRun(Base):
    __tablename__ = 'validation_runs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id'), index=True)
    fix_id: Mapped[str] = mapped_column(ForeignKey('proposed_fixes.id'), index=True)
    status: Mapped[str] = mapped_column(String, default='planned', index=True)
    plan_hash: Mapped[str] = mapped_column(String)
    manifest: Mapped[list] = mapped_column(JSON)
    snapshot: Mapped[dict] = mapped_column(JSON)
    policy: Mapped[dict] = mapped_column(JSON)
    proposed_sha256: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=now)
    expires_at: Mapped[str] = mapped_column(String)
    authorized_at: Mapped[str | None] = mapped_column(String, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String, default='viewer')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String, default=now)


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    csrf_token: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String, index=True)


class LoginThrottle(Base):
    __tablename__ = 'login_throttles'
    key: Mapped[str] = mapped_column(String, primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[str] = mapped_column(String)


class IncidentEvent(Base):
    __tablename__ = 'incident_events'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id'), index=True)
    action: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(Text, default='')
    evidence: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String, default=now)


class Job(Base):
    __tablename__ = 'jobs'
    __table_args__ = (UniqueConstraint('kind', 'target_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String)
    target_id: Mapped[str] = mapped_column(String)
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id'), index=True)
    status: Mapped[str] = mapped_column(String, default='queued', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class WorkerState(Base):
    __tablename__ = 'worker_state'
    id: Mapped[str] = mapped_column(String, primary_key=True, default='default')
    heartbeat_at: Mapped[str] = mapped_column(String, default=now)
