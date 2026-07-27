"""Tests for the LLM step.

The network call (_call_gemini) is patched out in every test, so these run
offline and for free. What is being tested is the parsing and the fallbacks -
the part that decides whether a bad response loses a user's job.
"""

import json

import pytest

from app.services import prompt as prompt_module
from app.services.prompt import PromptGenerationError, build_image_prompt

PRODUCT = "Florentine Wooden Salad Bowl"
DESCRIPTION = "Handpainted on mango wood, this compact salad bowl serves a supper for two."


def test_uses_the_llm_response_when_it_is_valid(monkeypatch):
    monkeypatch.setattr(prompt_module.settings, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(
        prompt_module,
        "_call_gemini",
        lambda _: json.dumps({"prompt": "a warm studio shot", "negative_prompt": "text, logos"}),
    )

    result = build_image_prompt(PRODUCT, DESCRIPTION)

    assert result["prompt"] == "a warm studio shot"
    assert result["negative_prompt"] == "text, logos"


def test_falls_back_when_the_response_is_not_json(monkeypatch):
    monkeypatch.setattr(prompt_module.settings, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(prompt_module, "_call_gemini", lambda _: "Sure! Here's a prompt:")

    result = build_image_prompt(PRODUCT, DESCRIPTION)

    # Template fallback, not an exception - a bad response must not lose the job.
    assert PRODUCT in result["prompt"]


def test_falls_back_when_the_prompt_is_empty(monkeypatch):
    monkeypatch.setattr(prompt_module.settings, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(
        prompt_module,
        "_call_gemini",
        lambda _: json.dumps({"prompt": "   ", "negative_prompt": "x"}),
    )

    result = build_image_prompt(PRODUCT, DESCRIPTION)

    assert PRODUCT in result["prompt"]


def test_uses_template_when_no_api_key_is_configured(monkeypatch):
    monkeypatch.setattr(prompt_module.settings, "GEMINI_API_KEY", "")

    result = build_image_prompt(PRODUCT, DESCRIPTION)

    assert PRODUCT in result["prompt"]
    assert result["negative_prompt"]


def test_raises_when_the_provider_is_unreachable(monkeypatch):
    """A dead provider is the one case that should fail the job."""

    def dead(_):
        raise PromptGenerationError("LLM unavailable: simulated outage")

    monkeypatch.setattr(prompt_module.settings, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(prompt_module, "_call_gemini", dead)

    with pytest.raises(PromptGenerationError):
        build_image_prompt(PRODUCT, DESCRIPTION)
