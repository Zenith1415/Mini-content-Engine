"""Where generated images live.

Kept separate from image generation on purpose: if we ever move to S3 or
Cloudflare R2, this file is the only thing that changes.
"""

import uuid
from pathlib import Path

from app.config import settings


def save_image(job_id: uuid.UUID, image_bytes: bytes) -> str:
    """Write the image to disk and return the URL it will be served from.

    Naming the file after the job id keeps this idempotent - if a job is ever
    retried it overwrites its own image instead of leaving orphans behind.
    """
    directory = Path(settings.STORAGE_DIR)
    directory.mkdir(parents=True, exist_ok=True)

    (directory / f"{job_id}.png").write_bytes(image_bytes)

    # main.py serves STORAGE_DIR at /images
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/images/{job_id}.png"
