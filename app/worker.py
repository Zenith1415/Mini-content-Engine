"""The content generation pipeline.

Runs in the background after POST /generate has already returned, so it opens
its own database session - the request's session is closed by then.

The one rule here: a job must never be left sitting in 'processing'. Every way
out of this function ends in 'completed' or 'failed'.
"""

import logging
import uuid

from app.db import SessionLocal
from app.models import Job, JobStatus
from app.services.images import fetch_reference_image, generate_image
from app.services.prompt import build_image_prompt
from app.services.storage import save_image

logger = logging.getLogger(__name__)


def run_job(job_id: uuid.UUID) -> None:
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
            # 1. Product info -> art-directed image prompt (LLM).
            prompt_data = build_image_prompt(job.product_name, job.description)
            job.generated_prompt = prompt_data["prompt"]
            db.commit()  # commit early so a poller can see the prompt land

            # 2. Fetch the product photo, if one was supplied.
            reference_image = fetch_reference_image(job.reference_image_url)

            # 3. Generate the new image from the prompt + that reference.
            image_bytes = generate_image(
                prompt=prompt_data["prompt"],
                negative_prompt=prompt_data["negative_prompt"],
                reference_image=reference_image,
            )

            # 4. Save it and hand back a URL we control.
            job.image_url = save_image(job.id, image_bytes)
            job.error_message = None
            job.status = JobStatus.COMPLETED
            db.commit()

            logger.info("Job %s completed -> %s", job_id, job.image_url)

        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            db.rollback()

            # Re-fetch: the rollback discarded our in-memory changes.
            failed_job = db.get(Job, job_id)
            if failed_job is not None:
                failed_job.status = JobStatus.FAILED
                failed_job.error_message = str(exc)[:500]
                db.commit()
    finally:
        db.close()
