"""Persistence layer — SQLAlchemy 2.x ORM models and DB write functions."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Index, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

UTC = timezone.utc


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    agent_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Span(Base):
    __tablename__ = "spans"
    __table_args__ = (Index("ix_spans_run_id", "run_id"),)

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(12), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Engine / session
# ---------------------------------------------------------------------------

def _db_path() -> str:
    override = os.environ.get("GLASSPIPE_DB_PATH")
    if override:
        return override
    default = Path.home() / ".glasspipe" / "traces.db"
    default.parent.mkdir(parents=True, exist_ok=True)
    return str(default)


def get_engine():
    path = _db_path()
    return create_engine(f"sqlite:///{path}")


def get_session() -> Session:
    return Session(get_engine())


_initialized_paths: set[str] = set()


def init_db() -> None:
    # Idempotent, but creating tables + probing migrations on every run start
    # is wasted work — do it once per DB path per process.
    path = _db_path()
    if path in _initialized_paths:
        return
    engine = get_engine()
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE runs ADD COLUMN agent_version TEXT"))
            conn.commit()
        except Exception:
            pass  # column already exists (pre-0.1.5 DBs get it added once)
    _initialized_paths.add(path)


# ---------------------------------------------------------------------------
# JSON safety
# ---------------------------------------------------------------------------

def _safe_json(obj) -> str | None:
    if obj is None:
        return None
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        print(
            f"glasspipe warning: value is not JSON-serializable; falling back to repr(). "
            f"Type: {type(obj).__name__}",
            file=sys.stderr,
        )
        return json.dumps(repr(obj))


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def write_run_start(run_id: str, name: str, agent_version: str | None = None) -> None:
    init_db()
    with get_session() as session:
        session.add(Run(
            id=run_id,
            name=name,
            agent_version=agent_version,
            started_at=datetime.now(UTC),
            status="running",
        ))
        session.commit()


def write_run_end(run_id: str, status: str, error_message: str | None = None) -> None:
    with get_session() as session:
        run = session.get(Run, run_id)
        if run is None:
            return
        run.ended_at = datetime.now(UTC)
        run.status = status
        run.error_message = error_message
        session.commit()


def write_span_start(
    span_id: str,
    run_id: str,
    parent_span_id: str | None,
    kind: str,
    name: str,
) -> None:
    with get_session() as session:
        session.add(Span(
            id=span_id,
            run_id=run_id,
            parent_span_id=parent_span_id,
            kind=kind,
            name=name,
            started_at=datetime.now(UTC),
            status="running",
        ))
        session.commit()


def write_span_end(
    span_id: str,
    status: str,
    input=None,
    output=None,
    metadata=None,
    error_message: str | None = None,
) -> None:
    with get_session() as session:
        span = session.get(Span, span_id)
        if span is None:
            return
        span.ended_at = datetime.now(UTC)
        span.status = status
        span.error_message = error_message
        span.input_json = _safe_json(input)
        span.output_json = _safe_json(output)
        span.metadata_json = _safe_json(metadata)
        session.commit()
