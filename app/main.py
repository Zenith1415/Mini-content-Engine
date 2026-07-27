import logging
from pathlib import Path
from uuid import UUID
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine, get_db
from app.models import Job, JobStatus
from app.schemas import GenerateRequest, GenerateResponse, JobResponse
from app.worker import run_job
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Must exist before StaticFiles is mounted below, or the mount raises on import.
Path(settings.STORAGE_DIR).mkdir(parents=True, exist_ok=True)

app = FastAPI(title="GlitrAI Mini Content Engine", version="0.1.0")
app.mount("/images", StaticFiles(directory=settings.STORAGE_DIR), name="images")

@app.get("/health")
def health():
    """Actually talks to Postgres - a health check that can't fail is useless."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        # Log the real error, but don't return it: database errors can contain
        # connection details, and this endpoint is unauthenticated.
        logger.exception("Health check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "error"},
        )

@app.post("/generate", response_model=GenerateResponse, status_code=202)
def generate(
    payload: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    job = Job(
        product_name=payload.product_name.strip(),
        description=payload.description.strip(),
        reference_image_url=str(payload.product_image_url) if payload.product_image_url else None,
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.commit()          
    db.refresh(job)
    background_tasks.add_task(run_job, job.id)
    return GenerateResponse(job_id=job.id, status=job.status)

@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_job(job)