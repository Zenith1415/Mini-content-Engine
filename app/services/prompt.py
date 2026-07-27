import json
import logging
import time

from app.config import settings

logger = logging.getLogger(__name__)

MODEL = "gemini-3.6-flash"

SYSTEM_PROMPT = """You are a product photography art director. You write prompts for an \
image generation model that will photograph a real product supplied as a reference image.

Given a product name and description, return ONE image prompt describing a single photograph.

Rules:
- Describe the SCENE, not the product's identity. The reference image already defines what
  the product looks like.
- Specify: camera framing and angle, lens character, lighting setup and direction,
  surface/background material, two or three styling props consistent with the product's use,
  colour palette, and mood.
- Only use materials, colours and finishes stated in the description. Never invent them.
- No text, no logos, no watermarks, no hands unless the description implies use.
- Photographic realism. 60-80 words. One paragraph, no line breaks.
- Also return a negative_prompt listing artifacts to avoid.

Return ONLY raw JSON in this exact shape:
{"prompt": "...", "negative_prompt": "..."}

Example
Input:
Product name: Florentine Wooden Salad Bowl
Description: A match made in summer - salads and wooden bowls. Handpainted on mango wood, \
this compact salad bowl serves a supper for two.
Output:
{"prompt": "Overhead three-quarter shot on a 50mm lens, the bowl centred on a sun-bleached \
linen runner over a pale oak table. Soft late-afternoon window light rakes in from the left, \
warm and directional, throwing a gentle shadow to the right. Styled with a crisp green salad, \
a small ceramic oil cruet and a scatter of cracked pepper. Muted summer palette of cream, \
olive and warm honey wood. Relaxed editorial food photography, shallow depth of field, \
natural texture.", "negative_prompt": "text, logos, watermark, harsh flash, plastic sheen, \
oversaturation, cluttered background, blurry, distorted proportions"}"""


class PromptGenerationError(RuntimeError):
    """Raised only when the LLM provider itself is unreachable."""


def _template_prompt(product_name: str, description: str) -> dict:
    """Deterministic fallback so a bad LLM response never kills a job."""
    return {
        "prompt": (
            f"Editorial product photograph of the {product_name} on a neutral linen surface, "
            "shot on a 50mm lens at a three-quarter angle. Soft directional daylight from the "
            "left with a gentle falloff, subtle natural shadows, warm muted palette, minimal "
            "styling props, shallow depth of field, photorealistic detail and true-to-life "
            f"materials. Context: {description}"
        ),
        "negative_prompt": (
            "text, logos, watermark, harsh flash, plastic sheen, oversaturation, "
            "cluttered background, blurry, distorted proportions"
        ),
    }


def _call_gemini(user_text: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=user_text,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.9,
                    # generous cap: Gemini 3 reasons before answering and those
                    # tokens count here, so a tight cap yields an empty response
                    max_output_tokens=2000,
                ),
            )
            return response.text or ""
        except Exception as exc:  # transient 429 / 5xx / network
            last_error = exc
            logger.warning("Gemini prompt call failed (attempt %s): %s", attempt + 1, exc)
            time.sleep(1.5 * (attempt + 1))

    raise PromptGenerationError(f"LLM unavailable: {last_error}")


def build_image_prompt(product_name: str, description: str) -> dict:
    if not settings.GEMINI_API_KEY:
        logger.info("No GEMINI_API_KEY set - using template prompt")
        return _template_prompt(product_name, description)

    user_text = f"Product name: {product_name}\nDescription: {description}"
    raw = _call_gemini(user_text)

    try:
        data = json.loads(raw)
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("model returned an empty prompt")
        negative = (data.get("negative_prompt") or "").strip() or None
        return {"prompt": prompt, "negative_prompt": negative}
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as exc:
        logger.warning("Unparseable LLM response (%s). Raw: %r", exc, raw[:500])
        return _template_prompt(product_name, description)