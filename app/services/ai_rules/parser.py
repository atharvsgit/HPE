from pydantic import BaseModel, Field
import json
from typing import List, Optional

class AIRuleResponse(BaseModel):
    sql: str
    explanation: str
    assumptions: List[str]
    possible_edge_cases: List[str]
    confidence_reasoning: str
    confidence: str

def parse_llm_response(response_text: str) -> AIRuleResponse:
    """
    Parse the LLM response safely, handling potential Markdown wrappers.
    """
    text = response_text.strip()
    
    # Strip markdown block if present
    if text.startswith("```json"):
        text = text[len("```json"):]
    elif text.startswith("```"):
        text = text[len("```"):]
        
    if text.endswith("```"):
        text = text[:-3]
        
    text = text.strip()
    
    try:
        data = json.loads(text)
        return AIRuleResponse(**data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {e}")
    except Exception as e:
        raise ValueError(f"Invalid response schema: {e}")
