from __future__ import annotations

import re


class SQLSafetyError(ValueError):
    def __init__(self, message: str, code: str = "INVALID_SQL") -> None:
        super().__init__(message)
        self.code = code


DANGEROUS_KEYWORDS = {
    "ALTER",
    "CALL",
    "COPY",
    "CREATE",
    "DELETE",
    "DO",
    "DROP",
    "GRANT",
    "INSERT",
    "MERGE",
    "REVOKE",
    "TRUNCATE",
    "UPDATE",
    "VACUUM",
}

UNSAFE_FUNCTIONS = {
    "dblink",
    "lo_export",
    "lo_import",
    "pg_ls_dir",
    "pg_read_binary_file",
    "pg_read_file",
    "pg_sleep",
}


def validate_safe_select(sql: str) -> None:
    stripped = _strip_comments(sql).strip()
    if not stripped:
        raise SQLSafetyError("SQL must not be empty.")

    _ensure_single_statement(stripped)
    token_text = _mask_quoted_literals(strip_trailing_semicolon(stripped))

    first_token = _first_token(token_text)
    if first_token != "SELECT":
        raise SQLSafetyError("Only single-statement SELECT queries are allowed.")

    dangerous = _find_token(token_text, DANGEROUS_KEYWORDS)
    if dangerous is not None:
        raise SQLSafetyError(f"Disallowed SQL keyword found: {dangerous}.", "DISALLOWED_SQL")

    unsafe_function = _find_function(token_text, UNSAFE_FUNCTIONS)
    if unsafe_function is not None:
        raise SQLSafetyError(
            f"Unsafe SQL function is not allowed: {unsafe_function}.",
            "DISALLOWED_SQL_FUNCTION",
        )


def strip_trailing_semicolon(sql: str) -> str:
    sql_without_comments = _strip_comments(sql).strip()
    if sql_without_comments.endswith(";"):
        return sql_without_comments[:-1].strip()
    return sql_without_comments


def _ensure_single_statement(sql: str) -> None:
    semicolon_count = 0
    for index, char in enumerate(_mask_quoted_literals(sql)):
        if char != ";":
            continue

        semicolon_count += 1
        if semicolon_count > 1 or sql[index + 1 :].strip():
            raise SQLSafetyError("Only one SQL statement is allowed.")


def _strip_comments(sql: str) -> str:
    output: list[str] = []
    index = 0
    quote: str | None = None

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if quote is None and char == "-" and next_char == "-":
            index += 2
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            continue

        if quote is None and char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(sql) and not (sql[index] == "*" and sql[index + 1] == "/"):
                index += 1
            index += 2
            continue

        output.append(char)

        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                if char == "'" and next_char == "'":
                    output.append(next_char)
                    index += 1
                else:
                    quote = None

        index += 1

    return "".join(output)


def _mask_quoted_literals(sql: str) -> str:
    output: list[str] = []
    index = 0
    quote: str | None = None

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if char in {"'", '"'}:
            if quote is None:
                quote = char
                output.append(" ")
            elif quote == char:
                output.append(" ")
                if char == "'" and next_char == "'":
                    output.append(" ")
                    index += 1
                else:
                    quote = None
            else:
                output.append(" ")
        elif quote is not None:
            output.append(" ")
        else:
            output.append(char)

        index += 1

    return "".join(output)


def _first_token(sql: str) -> str | None:
    match = re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql)
    if match is None:
        return None
    return match.group(0).upper()


def _find_token(sql: str, candidates: set[str]) -> str | None:
    for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql):
        token = match.group(0).upper()
        if token in candidates:
            return token
    return None


def _find_function(sql: str, candidates: set[str]) -> str | None:
    for candidate in candidates:
        if re.search(rf"\b{re.escape(candidate)}\s*\(", sql, flags=re.IGNORECASE):
            return candidate
    return None
