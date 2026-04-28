"""SQLAlchemy models for the hosted GlassPipe share API."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SharedTrace(Base):
    __tablename__ = "shared_traces"

    id: Mapped[str] = mapped_column(String(6), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    delete_token: Mapped[str] = mapped_column(String(32), nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
