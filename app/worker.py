import logging
import time
import uuid
from app.db import SessionLocal
from app.models import Job, JobStatus

logger = logging.getLogger(__name__)


def run_job(job_id: uuid.UUID) -> None:
    """PHASE 2 STUB: fakes the pipeline so the API can be tested end to end.
    Opens its own session - background tasks outlive the request session."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            logger.error("Job %s not found", job_id)
            return

        job.status = JobStatus.PROCESSING
        job.attempts += 1
        db.commit()

        try:
            time.sleep(3)  # stands in for the LLM + image generation
            job.generated_prompt = f"[stub prompt for {job.product_name}]"
            job.image_url = "https://placehold.co/1024x1024/png"
            job.error_message = None
            job.status = JobStatus.COMPLETED
            db.commit()
            logger.info("Job %s completed", job_id)

        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            db.rollback()
            failed = db.get(Job, job_id)
            if failed is not None:
                failed.status = JobStatus.FAILED
                failed.error_message = str(exc)[:500]
                db.commit()
    finally:
        db.close()