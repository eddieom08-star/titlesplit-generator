from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from src.config import get_settings
from src.database import init_db
from src.api.opportunities import router as opportunities_router
from src.api.scraper import router as scraper_router
from src.api.analyze import router as analyze_router
from src.api.properties import router as properties_router
from src.tasks.scheduler import start_scheduler, stop_scheduler

settings = get_settings()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Title Split Finder API")
    await init_db()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    logger.info("Shutting down Title Split Finder API")


app = FastAPI(
    title="Title Split Opportunity Finder",
    description="Automated property investment tool for identifying freehold blocks suitable for title splitting",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - use regex to properly match Vercel preview URLs
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://titlesplit-generator.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0", "build": "2026-01-13-v7-force"}


@app.get("/")
async def root():
    return {
        "name": "Title Split Opportunity Finder",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/debug/schema")
async def debug_schema():
    """Debug endpoint to check database schema."""
    from sqlalchemy import text
    from src.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            )
            tables = [row[0] for row in result.fetchall()]

            mi_columns = []
            if "manual_inputs" in tables:
                col_result = await session.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name = 'manual_inputs'")
                )
                mi_columns = [row[0] for row in col_result.fetchall()]

            alembic_version = None
            if "alembic_version" in tables:
                ver_result = await session.execute(text("SELECT version_num FROM alembic_version"))
                row = ver_result.fetchone()
                alembic_version = row[0] if row else None

            return {
                "tables": tables,
                "manual_inputs_columns": mi_columns,
                "alembic_version": alembic_version,
            }
    except Exception as e:
        return {"error": str(e), "error_type": type(e).__name__}


# Include routers
app.include_router(opportunities_router, prefix="/api")
app.include_router(scraper_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(properties_router, prefix="/api")
