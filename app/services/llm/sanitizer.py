import re
from typing import Any

# Basic regex patterns for PII
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"\b(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CC_REGEX = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
IP_REGEX = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")

class DataSanitizer:
    """Configurable security sanitization layer for LLM prompt data."""
    def __init__(
        self,
        mode: str = "denylist",
        denylist_fields: set[str] | None = None,
        allowlist_fields: set[str] | None = None,
        redact_patterns: bool = True
    ):
        self.mode = mode  # "denylist" or "allowlist"
        self.denylist_fields = denylist_fields or {"password", "secret", "token", "ssn", "credit_card", "email", "phone"}
        self.allowlist_fields = allowlist_fields or set()
        self.redact_patterns = redact_patterns

    def _should_mask_field(self, field_name: str) -> bool:
        field_lower = field_name.lower()
        if self.mode == "allowlist":
            return field_lower not in self.allowlist_fields
        
        for bad in self.denylist_fields:
            if bad in field_lower:
                return True
        return False

    def _mask_patterns(self, text: str) -> str:
        text = EMAIL_REGEX.sub("[EMAIL REDACTED]", text)
        text = PHONE_REGEX.sub("[PHONE REDACTED]", text)
        text = SSN_REGEX.sub("[SSN REDACTED]", text)
        text = CC_REGEX.sub("[CC REDACTED]", text)
        text = IP_REGEX.sub("[IP REDACTED]", text)
        return text

    def sanitize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Redacts sensitive fields and patterns, and applies length constraints."""
        sanitized = {}
        for k, v in row.items():
            if self._should_mask_field(k):
                sanitized[k] = "[FIELD REDACTED]"
                continue
            
            if isinstance(v, str):
                if len(v) > 80:
                    v = v[:80] + "...[TRUNCATED]"
                if self.redact_patterns:
                    v = self._mask_patterns(v)
            sanitized[k] = v
        return sanitized

# Global default instance
default_sanitizer = DataSanitizer()
