import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class ScrapeJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScrapeJob(Base):
    """Tracks scraper job execution and progress."""
    __tablename__ = "scrape_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default=ScrapeJobStatus.PENDING.value, index=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Results summary
    total_scraped: Mapped[int] = mapped_column(Integer, default=0)
    total_new: Mapped[int] = mapped_column(Integer, default=0)
    total_updated: Mapped[int] = mapped_column(Integer, default=0)

    # Per-source breakdown: {rightmove: {scraped: 10, new: 5, updated: 3}, zoopla: {...}}
    source_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def start(self) -> None:
        """Mark job as running and record start time."""
        self.status = ScrapeJobStatus.RUNNING.value
        self.started_at = datetime.utcnow()
        self.progress_percent = 0

    def complete(self, total_scraped: int, total_new: int, total_updated: int, source_results: dict) -> None:
        """Mark job as completed with final results."""
        self.status = ScrapeJobStatus.COMPLETED.value
        self.completed_at = datetime.utcnow()
        self.progress_percent = 100
        self.total_scraped = total_scraped
        self.total_new = total_new
        self.total_updated = total_updated
        self.source_results = source_results

    def fail(self, error_message: str) -> None:
        """Mark job as failed with error details."""
        self.status = ScrapeJobStatus.FAILED.value
        self.completed_at = datetime.utcnow()
        self.error_message = error_message

    def update_progress(self, percent: int, current_scraped: int = 0, current_new: int = 0, current_updated: int = 0) -> None:
        """Update job progress during execution."""
        self.progress_percent = min(max(percent, 0), 100)
        self.total_scraped = current_scraped
        self.total_new = current_new
        self.total_updated = current_updated

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate job duration in seconds."""
        if not self.started_at:
            return None
        end_time = self.completed_at or datetime.utcnow()
        return (end_time - self.started_at).total_seconds()

    @property
    def is_running(self) -> bool:
        """Check if job is currently running."""
        return self.status == ScrapeJobStatus.RUNNING.value

    @property
    def is_finished(self) -> bool:
        """Check if job has completed (success or failure)."""
        return self.status in (ScrapeJobStatus.COMPLETED.value, ScrapeJobStatus.FAILED.value)

    def __repr__(self) -> str:
        return f"<ScrapeJob {self.id} status={self.status} progress={self.progress_percent}%>"
