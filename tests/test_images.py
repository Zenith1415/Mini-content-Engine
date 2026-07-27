"""Tests for image generation and storage."""

import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.services import images as images_module
from app.services.images import ImageGenerationError, fetch_reference_image, generate_image
from app.services.storage import save_image

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_mock_provider_returns_a_real_png():
    image_bytes = generate_image("a warm studio shot of a wooden bowl")

    assert image_bytes.startswith(PNG_MAGIC)
    assert len(image_bytes) > 1000


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(images_module.settings, "IMAGE_PROVIDER", "bogus")

    with pytest.raises(ImageGenerationError):
        generate_image("anything")


def test_no_reference_url_returns_none():
    assert fetch_reference_image(None) is None
    assert fetch_reference_image("") is None


def test_broken_reference_url_returns_none_instead_of_raising():
    """A bad reference should downgrade the job to text-only, not fail it."""
    assert fetch_reference_image("http://127.0.0.1:1/not-a-server.jpg") is None


def test_save_image_writes_the_file_and_returns_its_url():
    job_id = uuid.uuid4()
    image_bytes = generate_image("a test image")

    url = save_image(job_id, image_bytes)

    path = Path(settings.STORAGE_DIR) / f"{job_id}.png"
    assert path.exists()
    assert path.read_bytes().startswith(PNG_MAGIC)
    assert url.endswith(f"/images/{job_id}.png")

    path.unlink()
