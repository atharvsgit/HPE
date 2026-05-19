import json
import httpx
from abc import ABC, abstractmethod

from app.llm.models import LLMRuleCandidate
from app.llm.prompts import build_prompt, SYSTEM_PROMPT
from app.settings import get_settings


class LLMProviderInterface(ABC):
    @abstractmethod
    async def generate_draft(self, intent: str) -> LLMRuleCandidate:
        pass


class MockLLMProvider(LLMProviderInterface):
    """A mock provider for testing or when no real LLM is configured."""
    async def generate_draft(self, intent: str) -> LLMRuleCandidate:
        return LLMRuleCandidate.model_validate(
            {
                "rule_name": "Mock Rule",
                "sql": "SELECT COUNT(*) AS violation_count FROM business_data.employees",
                "expected_result": {"type": "zero_violations"},
            }
        )

class GroqProvider(LLMProviderInterface):
    """A provider that calls the Groq API (OpenAI compatible)."""
    async def generate_draft(self, intent: str) -> LLMRuleCandidate:
        settings = get_settings()
        prompt = build_prompt(intent)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"}
                },
                timeout=settings.llm_request_timeout_seconds
            )
            if response.status_code != 200:
                raise RuntimeError(f"Groq API error: {response.text}")
            
            content = response.json()["choices"][0]["message"]["content"]
            return LLMRuleCandidate.model_validate_json(content)


def get_llm_provider() -> LLMProviderInterface:
    settings = get_settings()
    if settings.llm_provider == "groq" and settings.llm_api_key:
        return GroqProvider()
        
    return MockLLMProvider()
