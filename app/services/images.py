"""Image generation.

Two providers behind one function:

  mock   - draws a placeholder locally. No API key, no network, no cost.
           This is the default, and it is what the tests run against.
  gemini - the real thing: sends the prompt plus the product reference image
           to Gemini's image model.

Pick one with IMAGE_PROVIDER in .env. Everything upstream just calls
generate_image() and never learns which one ran.

Note: Gemini's free tier gives image models a quota of 0, so `gemini` needs a
billed key. The mock path exists so the whole pipeline still runs without one.
"""

import io
import logging
import textwrap
import time

import httpx
from PIL import Image, ImageDraw

from app.config import settings

logger = logging.getLogger(__name__)

IMAGE_MODEL = "gemini-3.1-flash-image"

# The reference URL comes from the user, so don't download unlimited bytes.
MAX_REFERENCE_BYTES = 10 * 1024 * 1024  # 10 MB


class ImageGenerationError(RuntimeError):
    """Image generation failed. The job will be marked failed."""


def fetch_reference_image(url: str | None) -> bytes | None:
    """Download the product image the user gave us.

    Returns None on any problem instead of raising: a broken reference should
    downgrade the job to text-only generation, not kill it.
    """
    if not url:
        return None

    try:
        response = httpx.get(url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            logger.warning("Reference URL is not an image (%s): %s", content_type, url)
            return None

        if len(response.content) > MAX_REFERENCE_BYTES:
            logger.warning("Reference image is too large (%s bytes), skipping", len(response.content))
            return None

        logger.info("Fetched reference image: %s bytes", len(response.content))
        return response.content

    except Exception as exc:
        logger.warning("Could not fetch reference image %s: %s", url, exc)
        return None


def _guess_mime_type(data: bytes) -> str:
    """Gemini needs to be told what kind of image it is being handed."""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _generate_mock(prompt: str, negative_prompt: str | None, reference_image: bytes | None) -> bytes:
    """Draw a placeholder image with the prompt written on it.

    Writing the prompt onto the image makes it obvious during a demo that the
    LLM step really ran and that this job produced this picture.
    """
    logger.info("Mock image generation: %.70s...", prompt)
    time.sleep(2)  # stand-in for real generation latency

    size = 1024
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)

    # Warm vertical gradient, so the placeholder doesn't look like a broken file.
    for y in range(size):
        shade = int(38 + (y / size) * 60)
        draw.line([(0, y), (size, y)], fill=(shade + 22, shade, shade - 6))

    draw.text((60, 60), "MOCK IMAGE", fill=(245, 240, 232))
    draw.text((60, 90), "IMAGE_PROVIDER=mock", fill=(180, 170, 158))
    draw.multiline_text(
        (60, 150),
        textwrap.fill(prompt, width=95),
        fill=(215, 205, 192),
        spacing=7,
    )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _generate_gemini(prompt: str, negative_prompt: str | None, reference_image: bytes | None) -> bytes:
    """Real generation. Imported here so mock mode never needs the SDK."""
    if not settings.GEMINI_API_KEY:
        raise ImageGenerationError("GEMINI_API_KEY is not set")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    text = prompt
    if negative_prompt:
        text = f"{text}\n\nAvoid: {negative_prompt}"

    contents = []
    if reference_image:
        contents.append(
            types.Part.from_bytes(
                data=reference_image,
                mime_type=_guess_mime_type(reference_image),
            )
        )
        # Without this instruction the model treats the reference as loose
        # inspiration and invents a different product, which defeats the point.
        text = (
            "Using the product in the supplied reference image, keeping its shape, "
            "material, colour and proportions exactly, photograph it in this scene:\n\n"
            + text
        )
    contents.append(text)

    try:
        response = client.models.generate_content(model=IMAGE_MODEL, contents=contents)
    except Exception as exc:
        raise ImageGenerationError(f"Gemini image request failed: {exc}") from exc

    # The response is a mixed list - the model often returns a text part next to
    # the image - so look for the first part that actually carries image bytes.
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                return part.inline_data.data

    raise ImageGenerationError("Gemini returned no image data")


def generate_image(
    prompt: str,
    negative_prompt: str | None = None,
    reference_image: bytes | None = None,
) -> bytes:
    """Generate an image and return the raw PNG/JPEG bytes.

    Returns bytes rather than a URL on purpose: provider URLs expire, so we
    save the file ourselves (see services/storage.py).
    """
    provider = settings.IMAGE_PROVIDER.lower()

    if provider == "mock":
        return _generate_mock(prompt, negative_prompt, reference_image)
    if provider == "gemini":
        return _generate_gemini(prompt, negative_prompt, reference_image)

    raise ImageGenerationError(f"Unknown IMAGE_PROVIDER: {settings.IMAGE_PROVIDER!r}")
