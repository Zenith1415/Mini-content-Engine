"""End-to-end tests for the API.

These need Postgres running. TestClient runs background tasks before it returns
the response, so a job is already finished by the time the POST comes back -
against the real server you would see pending -> processing -> completed across
separate requests instead.
"""

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)

PAYLOAD = {
    "product_name": "Florentine Wooden Salad Bowl",
    "description": (
        "A match made in summer - salads and wooden bowls. Handpainted on mango wood, "
        "this compact salad bowl serves a supper for two."
    ),
}


def test_generate_then_fetch_the_finished_job():
    created = client.post("/generate", json=PAYLOAD)

    assert created.status_code == 202
    job_id = created.json()["job_id"]
    assert created.json()["status"] == "pending"

    fetched = client.get(f"/jobs/{job_id}")
    assert fetched.status_code == 200

    job = fetched.json()
    assert job["status"] == "completed", job["error"]
    assert job["generated_prompt"]
    assert job["image_url"].endswith(f"/images/{job_id}.png")
    assert job["error"] is None

    # the image really was written, not just recorded
    image_path = Path(settings.STORAGE_DIR) / f"{job_id}.png"
    assert image_path.exists()
    image_path.unlink()


def test_unknown_job_returns_404():
    response = client.get(f"/jobs/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_malformed_job_id_returns_422():
    assert client.get("/jobs/not-a-uuid").status_code == 422


def test_blank_product_name_is_rejected():
    response = client.post("/generate", json={"product_name": "", "description": "x"})

    assert response.status_code == 422


def test_missing_description_is_rejected():
    assert client.post("/generate", json={"product_name": "Bowl"}).status_code == 422


def test_invalid_reference_url_is_rejected():
    response = client.post(
        "/generate",
        json={"product_name": "Bowl", "description": "x", "product_image_url": "not-a-url"},
    )

    assert response.status_code == 422
