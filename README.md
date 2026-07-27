# Mini Content Engine

Takes a product name, a short description and (optionally) a product photo, and
turns them into AI-generated creative.

The interesting part isn't the API - it's what happens between the request and
the image. A one-line product description is a bad image prompt. So the service
first sends it to an LLM acting as a product photography art director, which
turns it into a proper prompt (framing, lens, lighting direction, surface,
styling props, palette), and only then generates the image from that prompt plus
the product reference photo.

Image generation takes 5-60 seconds, so `POST /generate` doesn't wait for it. It
writes a job row, returns a job id immediately, and does the work in the
background. Clients poll `GET /jobs/{id}`.

```
POST /generate
      |
      +-- write job row (pending), return 202 + job_id
      |
      +-- background:
            pending -> processing
                 1. LLM writes an art-directed image prompt
                 2. download the product reference image
                 3. generate the image from prompt + reference
                 4. save it, store the URL
            -> completed   (or failed, with the reason)
```

## Quickstart

Needs Docker and Python 3.11+.

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows; use .venv/bin/activate elsewhere
pip install -r requirements.txt

cp .env.example .env               # works as-is; add a Gemini key for real prompts

docker compose up -d               # Postgres
alembic upgrade head               # create the jobs table

uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive API.

It runs out of the box with no API key: without one the prompt step falls back to
a template and the image step draws a placeholder. Add a key from
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) to see the real
LLM prompts.

## Configuration

All settings come from `.env` (see `.env.example`).

| Variable | Default | What it does |
| --- | --- | --- |
| `POSTGRES_USER` / `_PASSWORD` / `_DB` | `glitr` | Database credentials. Docker Compose reads the same values, so they're defined once. |
| `POSTGRES_HOST` / `_PORT` | `localhost` / `5432` | Where Postgres is. |
| `GEMINI_API_KEY` | *(empty)* | Leave empty to use the template prompt. |
| `IMAGE_PROVIDER` | `mock` | `mock` or `gemini`. |
| `STORAGE_DIR` | `./storage` | Where generated images are written. |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Prefix for returned image URLs. |

## Endpoints

### `GET /health`

```bash
curl localhost:8000/health
```
```json
{"status": "ok", "database": "ok"}
```

Runs a real `SELECT 1` and returns 503 if the database is unreachable.

### `POST /generate`

```bash
curl -X POST localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "Florentine Wooden Salad Bowl",
    "description": "A match made in summer - salads and wooden bowls. Handpainted on mango wood, this compact salad bowl serves a supper for two.",
    "product_image_url": "https://example.com/bowl.jpg"
  }'
```
```json
{"job_id": "a75701d9-ea90-45cd-bf57-b99e574ec0d4", "status": "pending"}
```

Returns `202 Accepted` in a few hundred milliseconds. `product_image_url` is
optional. Invalid input returns `422` and no job is created.

### `GET /jobs/{job_id}`

```bash
curl localhost:8000/jobs/a75701d9-ea90-45cd-bf57-b99e574ec0d4
```
```json
{
  "job_id": "a75701d9-ea90-45cd-bf57-b99e574ec0d4",
  "status": "completed",
  "product_name": "Florentine Wooden Salad Bowl",
  "description": "A match made in summer - salads and wooden bowls...",
  "reference_image_url": "https://example.com/bowl.jpg",
  "generated_prompt": "High-angle three-quarter shot taken on an 85mm lens, focusing on the bowl placed on a warm, natural wooden surface. Soft, directional summer sunlight streams in from the side, casting gentle shadows and highlighting natural textures. Styled for a supper for two with a fresh green salad inside the bowl, accompanied by a small glass dressing cruet and wooden serving utensils...",
  "image_url": "http://localhost:8000/images/a75701d9-ea90-45cd-bf57-b99e574ec0d4.png",
  "error": null,
  "created_at": "2026-07-27T13:22:46.500951Z",
  "updated_at": "2026-07-27T13:22:57.678179Z"
}
```

`status` is one of `pending`, `processing`, `completed`, `failed`. When it's
`failed`, `error` says why. Unknown ids return `404`; malformed ones return `422`.

Generated images are served from `/images/{job_id}.png`.

## Layout

```
app/
  main.py              FastAPI app and the three endpoints
  worker.py            the background pipeline
  models.py            the jobs table
  schemas.py           request/response shapes
  db.py, config.py     engine, session, settings
  services/
    prompt.py          product info -> image prompt (LLM)
    images.py          image generation (mock / gemini) + reference download
    storage.py         saving images and building their URLs
migrations/            Alembic
tests/
```

## Tests

```bash
docker compose up -d && alembic upgrade head
pytest
```

18 tests, and they cost nothing: `tests/conftest.py` forces `IMAGE_PROVIDER=mock`
and blanks the API key, so no network calls happen. The Gemini call itself is
monkeypatched out, which lets the tests cover the parts that actually decide
whether a user loses their job - JSON parsing, the fallbacks, and the failure
paths.

They do need Postgres running. It's the real database rather than SQLite because
the schema relies on Postgres types and constraints, and testing against a
different engine than production is how you find out too late.

## Design decisions

**202 and polling, not a blocking request.** Generation is far too slow to hold a
connection open. The job row is the single source of truth; the API only reads
and writes it.

**A provider seam for image generation.** `generate_image()` dispatches on one
env var. That's what makes the tests free and offline, lets a reviewer run the
whole thing with no API key, and keeps the real implementation one config change
away.

**Degrade rather than fail.** A reference image that 404s falls back to text-only
generation. An unparseable LLM response falls back to a template prompt. Only a
genuinely dead provider fails the job - losing someone's work because a model
returned malformed JSON isn't acceptable when a decent deterministic prompt is
one function call away.

**No job may be left in `processing`.** Every exit from `run_job()` ends in
`completed` or `failed` with a readable reason.

**The status values are a database CHECK constraint,** not just an application
convention. If some future code path tries to write a bad status, Postgres
rejects it.

**UUID job ids** so they can't be enumerated and don't leak how many jobs exist.

**`/health` doesn't return the error text.** It's unauthenticated, and database
errors carry connection details. The real error goes to the logs.

**Images are stored as files, not in Postgres.** `bytea` columns bloat the
database and its backups for no benefit. `storage.py` is the only file that
changes if this moves to S3.

## Known limitations

**Gemini's free tier can't generate images.** Every image model returns
`429 RESOURCE_EXHAUSTED ... limit: 0` on a free key - it's not a daily cap, image
generation simply requires billing. So `IMAGE_PROVIDER=gemini` is implemented but
has not been run end to end; the default `mock` provider draws a placeholder with
the generated prompt written on it. The LLM prompt step *is* real and does run on
the free tier.

**Background tasks run in the API process.** If the server restarts mid-job, that
job stays in `processing` forever. Fine for this scope, not for production - see
below.

**No retries.** The `attempts` column is populated but nothing acts on it yet.

**No auth, no rate limiting.** Anyone who can reach the service can queue work
against your API quota.

## What I'd do next

1. **Move the worker out of the web process.** A separate process polling
   `SELECT ... FROM jobs WHERE status='pending' FOR UPDATE SKIP LOCKED LIMIT 1`.
   `SKIP LOCKED` is the whole trick - several workers can pull jobs concurrently
   without ever handing the same row to two of them, and it needs no Redis. That
   fixes the stranded-job problem and scales horizontally.
2. **A reaper** for jobs stuck in `processing` past a timeout, retried using the
   `attempts` column with backoff.
3. **S3 or R2** instead of local disk, with presigned URLs.
4. **Webhooks** as an alternative to polling.
5. **`GET /jobs`** with pagination and status filtering, plus an index on
   `created_at`.
6. **Per-key rate limiting** and an API key on `/generate`.
