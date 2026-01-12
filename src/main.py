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
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/")
async def root():
    return {
        "name": "Title Split Opportunity Finder",
        "version": "0.1.0",
        "docs": "/docs",
    }


# Include routers
app.include_router(opportunities_router, prefix="/api")
app.include_router(scraper_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(properties_router, prefix="/api")
