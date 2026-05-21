import re

class PromptInjectionError(ValueError):
    pass

FORBIDDEN_PROMPT_PATTERNS = [
    r"ignore previous\s*(instructions|prompts?)",
    r"return all tables",
    r"show hidden schemas",
    r"system prompt",
    r"you are now\s*(a|an)?\s*(unrestricted|admin)",
    r"bypass\s*(rules|validation|safety)",
    r"drop\s+(table|database)",
]

def sanitize_prompt(prompt: str) -> str:
    """
    Sanitize the natural language prompt against prompt injection
    and schema exfiltration attempts.
    """
    if not prompt:
        raise ValueError("Prompt cannot be empty.")
    
    prompt_lower = prompt.lower()
    
    for pattern in FORBIDDEN_PROMPT_PATTERNS:
        if re.search(pattern, prompt_lower):
            raise PromptInjectionError("Detected potential prompt injection or unsafe instructions.")
    
    # Enforce a max length to prevent overly long context attacks
    if len(prompt) > 2000:
        raise PromptInjectionError("Prompt exceeds maximum allowed length.")
        
    return prompt.strip()
