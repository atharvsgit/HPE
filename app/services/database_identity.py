from __future__ import annotations

import hashlib
import json
from typing import Any


def build_database_connection_fingerprint(connection: Any) -> str:
    payload = database_connection_identity_params(connection)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def database_connection_identity_params(connection: Any) -> dict[str, Any]:
    return {
        "db_type": str(connection.db_type).strip().lower(),
        "host": str(connection.host).strip().lower(),
        "port": int(connection.port),
        "database": str(connection.database).strip().lower(),
        "username": str(connection.username).strip().lower(),
    }
