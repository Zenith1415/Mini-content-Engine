"""Test setup.

These env vars are set before anything imports app.config, so the whole test
suite runs against the mock image provider and the template prompt - no API
key, no network calls, no cost. Environment variables win over .env values.

The tests do need Postgres running (docker compose up -d) and migrations
applied (alembic upgrade head).
"""

import os

os.environ["IMAGE_PROVIDER"] = "mock"
os.environ["GEMINI_API_KEY"] = ""
