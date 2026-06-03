from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def generate_json(self, prompt: str, system_prompt: str) -> dict:
        """Generates a structured JSON response from the LLM."""
        pass
