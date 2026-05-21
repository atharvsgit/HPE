from app.daemon.sql_safety import (
    validate_safe_select,
    SQLSafetyError,
    _strip_comments,
    _mask_quoted_literals,
)
import re

AI_DISALLOWED_KEYWORDS = {
    "CROSS JOIN",
    "LATERAL",
    "COPY",
    "EXPORT",
    "INFORMATION_SCHEMA",
    "PG_CATALOG",
    "INTO",
    "OVER", # to block window functions temporarily
}

INJECTION_ARTIFACTS = {
    "ignore previous instructions",
    "system prompt",
    "system command",
    "you are now",
}


def validate_ai_generated_sql(sql: str) -> None:
    # 1. Use the base platform SQL validator
    validate_safe_select(sql)

    # 2. Check for AI-specific constraints
    stripped_sql = _strip_comments(sql).strip()
    masked_sql = _mask_quoted_literals(stripped_sql).upper()

    # Deny SELECT *
    if re.search(r"SELECT\s+\*\s+FROM", masked_sql, re.IGNORECASE):
        raise SQLSafetyError("SELECT * is not allowed. Please explicitly select columns or aggregates.", code="AI_SELECT_STAR_BLOCKED")

    # Deny disallowed keywords for AI scope (CROSS JOIN, LATERAL, COPY, EXPORT, window functions, etc.)
    for keyword in AI_DISALLOWED_KEYWORDS:
        if keyword in masked_sql:
            raise SQLSafetyError(f"Keyword '{keyword}' is not allowed in AI-generated rules.", code="AI_KEYWORD_BLOCKED")

    # Extract comments from the original SQL and check for injection artifacts
    comments = []
    index = 0
    quote = None
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if quote is None and char == "-" and next_char == "-":
            start = index
            index += 2
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            comments.append(sql[start:index])
            continue

        if quote is None and char == "/" and next_char == "*":
            start = index
            index += 2
            while index + 1 < len(sql) and not (sql[index] == "*" and sql[index + 1] == "/"):
                index += 1
            index += 2
            comments.append(sql[start:index])
            continue

        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                if char == "'" and next_char == "'":
                    index += 1
                else:
                    quote = None
        index += 1

    comments_str = " ".join(comments).lower()
    for artifact in INJECTION_ARTIFACTS:
        if artifact in comments_str:
            raise SQLSafetyError("Prompt injection artifacts detected in SQL comments.", code="AI_INJECTION_ARTIFACT")

    # The prompt required 'violation_count' as alias
    if "VIOLATION_COUNT" not in masked_sql:
        raise SQLSafetyError("AI rule must return a single numeric output aliased as 'violation_count'.", code="AI_MISSING_ALIAS")
