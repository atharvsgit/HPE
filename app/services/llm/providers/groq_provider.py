from __future__ import annotations

import json
import logging

import groq as groq_sdk
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.services.llm.providers.base import LLMProvider
from app.settings import get_settings

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    """
    Concrete LLM provider backed by the GROQ API.
    Uses the official `groq` SDK with async client.
    """

    def __init__(self) -> None:
        settings = get_settings()
        # Enforce 10s timeout to prevent hanging workers
        self._client = groq_sdk.AsyncGroq(api_key=settings.groq_api_key, timeout=10.0)
        self._model = settings.llm_model

    @retry(
        retry=retry_if_exception_type((
            groq_sdk.RateLimitError,
            groq_sdk.APIConnectionError,
            groq_sdk.APITimeoutError,
            groq_sdk.InternalServerError,
        )),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_json(self, prompt: str, system_prompt: str) -> dict:
        """
        Sends prompt to Groq and returns a parsed JSON dict.
        Raises ValueError if the response cannot be parsed as JSON.
        """
        chat_completion = await self._client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            model=self._model,
            temperature=0.3,
            response_format={"type": "json_object"} # Ensure JSON mode if supported
        )

        raw = chat_completion.choices[0].message.content or ""
        tokens = chat_completion.usage.total_tokens if chat_completion.usage else 0
        logger.debug(
            "Groq response received. model=%s tokens_used=%s",
            self._model,
            tokens,
        )

        # Strip markdown code fences if the model wrapped its output
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            parsed = json.loads(cleaned)
            # Inject metadata for observability
            parsed["_meta"] = {
                "provider_name": "groq",
                "model_name": self._model,
                "token_usage": tokens
            }
            return parsed
        except json.JSONDecodeError as exc:
            raise ValueError(f"Groq returned non-JSON output: {exc}") from exc
