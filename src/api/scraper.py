"""API endpoints for triggering and monitoring scraper tasks."""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.tasks.scraping import scrape_all_sources, scrape_rightmove
from src.tasks.enrichment import enrich_pending_properties
from src.database import AsyncSessionLocal, get_db
from src.models.property import Property
from src.models.scrape_job import ScrapeJob

logger = structlog.get_logger()
router = APIRouter(prefix="/scraper", tags=["scraper"])

# In-memory tracking for current running job
_current_job_id: Optional[uuid.UUID] = None


class JobSummary(BaseModel):
    """Summary of a scrape job."""
    id: uuid.UUID
    status: str
    progress_percent: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_scraped: int
    total_new: int
    source_results: Optional[dict] = None


class StatusResponse(BaseModel):
    """Response for scraper status endpoint."""
    current_status: str  # "running" | "idle"
    current_job: Optional[JobSummary] = None
    last_completed: Optional[JobSummary] = None


class TriggerResponse(BaseModel):
    """Response for scrape trigger endpoint."""
    status: str
    message: str
    job_id: uuid.UUID


def _job_to_summary(job: ScrapeJob) -> JobSummary:
    """Convert ScrapeJob model to JobSummary response."""
    return JobSummary(
        id=job.id,
        status=job.status,
        progress_percent=job.progress_percent,
        started_at=job.started_at,
        completed_at=job.completed_at,
        total_scraped=job.total_scraped,
        total_new=job.total_new,
        source_results=job.source_results,
    )


@router.get("/status", response_model=StatusResponse)
async def get_scraper_status(db: AsyncSession = Depends(get_db)):
    """
    Get current scraper status.

    Returns whether scraper is running/idle, current job details if running,
    and last completed job details.
    """
    global _current_job_id

    current_job = None
    current_status = "idle"

    # Check if there's a running job
    if _current_job_id:
        result = await db.execute(
            select(ScrapeJob).where(ScrapeJob.id == _current_job_id)
        )
        job = result.scalar_one_or_none()
        if job and job.status == "running":
            current_status = "running"
            current_job = _job_to_summary(job)
        else:
            # Job finished, clear the tracking
            _current_job_id = None

    # Get last completed job
    result = await db.execute(
        select(ScrapeJob)
        .where(ScrapeJob.status.in_(["completed", "failed"]))
        .order_by(desc(ScrapeJob.completed_at))
        .limit(1)
    )
    last_job = result.scalar_one_or_none()
    last_completed = _job_to_summary(last_job) if last_job else None

    return StatusResponse(
        current_status=current_status,
        current_job=current_job,
        last_completed=last_completed,
    )


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    """
    List recent scrape jobs (last 10).

    Returns jobs ordered by start time, most recent first.
    """
    result = await db.execute(
        select(ScrapeJob)
        .order_by(desc(ScrapeJob.started_at))
        .limit(10)
    )
    jobs = result.scalars().all()
    return [_job_to_summary(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=JobSummary)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Get details for a specific scrape job.
    """
    result = await db.execute(
        select(ScrapeJob).where(ScrapeJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return _job_to_summary(job)


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_scrape(background_tasks: BackgroundTasks):
    """
    Trigger a full scrape of all sources.

    Creates a ScrapeJob record and runs scrape in background.
    Returns the job_id for tracking progress.
    """
    global _current_job_id

    # Check if already running
    if _current_job_id:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ScrapeJob).where(ScrapeJob.id == _current_job_id)
            )
            existing_job = result.scalar_one_or_none()
            if existing_job and existing_job.status == "running":
                raise HTTPException(
                    status_code=409,
                    detail=f"Scrape already running with job_id: {_current_job_id}"
                )

    # Create new job record
    job_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        job = ScrapeJob(
            id=job_id,
            status="running",
            progress_percent=0,
            started_at=datetime.utcnow(),
            total_scraped=0,
            total_new=0,
            source_results={},
        )
        session.add(job)
        await session.commit()

    _current_job_id = job_id
    background_tasks.add_task(run_scrape, job_id)

    return TriggerResponse(
        status="started",
        message="Scrape job triggered in background",
        job_id=job_id,
    )


@router.post("/trigger/rightmove")
async def trigger_rightmove_scrape(
    location: str = "london",
    background_tasks: BackgroundTasks = None,
):
    """
    Trigger a Rightmove scrape for a specific location.
    """
    background_tasks.add_task(run_rightmove_scrape, location)
    return {"status": "started", "location": location}


@router.post("/enrich")
async def trigger_enrichment(
    batch_size: int = 10,
    background_tasks: BackgroundTasks = None,
):
    """
    Trigger enrichment of pending properties.

    Fetches EPC data, comparables, and runs AI analysis.
    """
    background_tasks.add_task(run_enrichment, batch_size)
    return {"status": "started", "batch_size": batch_size}


async def run_scrape(job_id: uuid.UUID):
    """Run full scrape with job progress tracking."""
    global _current_job_id

    try:
        logger.info("Starting manual scrape trigger", job_id=str(job_id))

        # Update job to 10% - starting
        await _update_job_progress(job_id, 10)

        results = await scrape_all_sources()

        # Update job with results
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ScrapeJob).where(ScrapeJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if job:
                job.status = "completed"
                job.progress_percent = 100
                job.completed_at = datetime.utcnow()
                job.total_scraped = results.get("total_scraped", 0)
                job.total_new = results.get("total_new", 0)
                job.source_results = results.get("sources", {})
                await session.commit()

        logger.info("Manual scrape completed", job_id=str(job_id), **results)

    except Exception as e:
        logger.error("Manual scrape failed", job_id=str(job_id), error=str(e))

        # Update job as failed
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ScrapeJob).where(ScrapeJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if job:
                job.status = "failed"
                job.completed_at = datetime.utcnow()
                job.source_results = {"error": str(e)}
                await session.commit()

    finally:
        _current_job_id = None


async def _update_job_progress(job_id: uuid.UUID, progress: int, source_results: dict = None):
    """Update job progress in database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ScrapeJob).where(ScrapeJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job:
            job.progress_percent = progress
            if source_results:
                job.source_results = source_results
            await session.commit()


async def run_rightmove_scrape(location: str):
    """Run Rightmove scrape for location."""
    try:
        logger.info("Starting Rightmove scrape", location=location)
        results = await scrape_rightmove(location)
        logger.info("Rightmove scrape completed", **results)
    except Exception as e:
        logger.error("Rightmove scrape failed", error=str(e))


async def run_enrichment(batch_size: int):
    """Run enrichment."""
    try:
        logger.info("Starting enrichment", batch_size=batch_size)
        results = await enrich_pending_properties(batch_size=batch_size)
        logger.info("Enrichment completed", **results)
    except Exception as e:
        logger.error("Enrichment failed", error=str(e))


@router.delete("/demo")
async def clear_demo_data():
    """
    Remove all demo properties from the database.
    """
    from sqlalchemy import delete

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(Property).where(Property.source == "demo")
        )
        await session.commit()
        deleted = result.rowcount

    logger.info("Demo data cleared", count=deleted)
    return {"status": "cleared", "count": deleted}
