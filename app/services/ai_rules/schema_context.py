from sqlalchemy import text
from app.db.session import executor_engine
import json

async def get_schema_context(schema_name: str, table_name: str, max_tokens: int = 1500) -> str:
    """
    Fetch and format budget-aware schema context for LLM generation.
    Prioritizes table name, columns, data types, and relationships.
    """
    async with executor_engine.connect() as conn:
        # Get columns
        columns_result = await conn.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                ORDER BY ordinal_position
                """
            ),
            {"schema_name": schema_name, "table_name": table_name},
        )
        columns = columns_result.mappings().all()

        # Get foreign keys
        fks_result = await conn.execute(
            text(
                """
                SELECT
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM
                    information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                      ON ccu.constraint_name = tc.constraint_name
                      AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = :schema_name
                  AND tc.table_name = :table_name
                """
            ),
            {"schema_name": schema_name, "table_name": table_name},
        )
        foreign_keys = fks_result.mappings().all()

    # Format output
    schema_info = {
        "table": f"{schema_name}.{table_name}",
        "columns": [
            {
                "name": col["column_name"],
                "type": col["data_type"],
                "nullable": col["is_nullable"] == "YES"
            }
            for col in columns
        ],
        "relationships": [
            {
                "column": fk["column_name"],
                "references_table": fk["foreign_table_name"],
                "references_column": fk["foreign_column_name"]
            }
            for fk in foreign_keys
        ]
    }
    
    context_str = json.dumps(schema_info, indent=2)
    
    # Budget aware truncation (approximate by chars)
    max_chars = max_tokens * 4
    if len(context_str) > max_chars:
        # If too large, we just strip relationships first, then truncate columns if needed
        schema_info.pop("relationships", None)
        context_str = json.dumps(schema_info, indent=2)
        if len(context_str) > max_chars:
            schema_info["columns"] = schema_info["columns"][:max_chars//100] # Very rough truncation
            schema_info["truncated"] = True
            context_str = json.dumps(schema_info, indent=2)
            
    return context_str
