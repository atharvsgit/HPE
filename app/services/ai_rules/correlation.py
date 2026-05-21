import math
import json
import logging
from collections import Counter
from sqlalchemy import text
from app.db.session import metadata_engine

logger = logging.getLogger(__name__)

# --- Lightweight Fallback Embedding / Similarity Engine ---
# In a production environment, this should be replaced with a real embedding API
# (e.g., OpenAI embeddings) and a vector database (e.g., pgvector).
# Here we use a local TF-IDF style approach to generate a sparse "embedding" vector
# represented as a dictionary of word frequencies.

def _tokenize(text_data: str) -> list[str]:
    return "".join(c if c.isalnum() else " " for c in text_data.lower()).split()

def _generate_sparse_embedding(text_data: str) -> dict[str, int]:
    tokens = _tokenize(text_data)
    # Filter out very common stopwords if necessary, keep it simple for now
    return dict(Counter(tokens))

def _cosine_similarity(vec1: dict[str, int], vec2: dict[str, int]) -> float:
    intersection = set(vec1.keys()) & set(vec2.keys())
    dot_product = sum(vec1[k] * vec2[k] for k in intersection)
    
    mag1 = math.sqrt(sum(v**2 for v in vec1.values()))
    mag2 = math.sqrt(sum(v**2 for v in vec2.values()))
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot_product / (mag1 * mag2)

def _get_matched_keywords(vec1: dict[str, int], vec2: dict[str, int]) -> list[str]:
    intersection = set(vec1.keys()) & set(vec2.keys())
    # Sort by combined frequency
    sorted_keywords = sorted(list(intersection), key=lambda k: vec1[k] + vec2[k], reverse=True)
    return sorted_keywords[:5]  # Top 5 shared concepts

async def index_incident(batch_id: int, rule_id: int, summary_text: str, severity: str):
    """
    Called asynchronously after a batch is summarized.
    Generates an embedding for the incident and stores it.
    """
    if not summary_text:
        return

    # Sanitize and build the indexable text
    # We include rule metadata and severity but EXCLUDE raw rows
    incident_text = f"Severity {severity}. {summary_text}"
    embedding = _generate_sparse_embedding(incident_text)
    
    async with metadata_engine.begin() as conn:
        # Check if already indexed
        exists = await conn.execute(
            text("SELECT 1 FROM dq_results.incident_embeddings WHERE violation_batch_id = :batch_id"),
            {"batch_id": batch_id}
        )
        if exists.scalar_one_or_none():
            return
            
        await conn.execute(
            text("""
                INSERT INTO dq_results.incident_embeddings (violation_batch_id, rule_id, incident_text, embedding)
                VALUES (:batch_id, :rule_id, :incident_text, :embedding)
            """),
            {
                "batch_id": batch_id,
                "rule_id": rule_id,
                "incident_text": incident_text,
                "embedding": json.dumps(embedding)
            }
        )
    logger.info(f"Indexed incident for batch {batch_id}")

async def find_similar_incidents(batch_id: int, threshold: float = 0.3) -> list[dict]:
    """
    Finds historically similar incidents.
    Requires explainability: score, matched concepts, rationale.
    """
    async with metadata_engine.connect() as conn:
        # Get target incident
        target_res = await conn.execute(
            text("""
                SELECT embedding, incident_text, rule_id 
                FROM dq_results.incident_embeddings 
                WHERE violation_batch_id = :batch_id
            """),
            {"batch_id": batch_id}
        )
        target_row = target_res.mappings().first()
        if not target_row:
            return []
            
        target_vec = target_row["embedding"]
        if isinstance(target_vec, str):
            target_vec = json.loads(target_vec)
            
        # Get historical incidents (for now, fetch all and compute in python; 
        # with pgvector this would be an exact DB query).
        historical_res = await conn.execute(
            text("""
                SELECT e.violation_batch_id, e.rule_id, e.embedding, e.incident_text, e.created_at,
                       b.status, s.summary, f.edited_summary
                FROM dq_results.incident_embeddings e
                JOIN dq_results.violation_batches b ON b.id = e.violation_batch_id
                LEFT JOIN dq_results.llm_summaries s ON s.violation_batch_id = b.id
                LEFT JOIN dq_results.llm_feedback f ON f.violation_batch_id = b.id AND f.feedback_type IN ('edit', 'accept')
                WHERE e.violation_batch_id != :batch_id
                ORDER BY e.created_at DESC
                LIMIT 100
            """),
            {"batch_id": batch_id}
        )
        history = historical_res.mappings().all()

    results = []
    for h in history:
        h_vec = h["embedding"]
        if isinstance(h_vec, str):
            h_vec = json.loads(h_vec)
            
        score = _cosine_similarity(target_vec, h_vec)
        if score >= threshold:
            matched_keywords = _get_matched_keywords(target_vec, h_vec)
            # Explainability rationale
            rationale = "High semantic overlap in terminology." if score > 0.6 else "Moderate conceptual similarities found."
            if h["rule_id"] == target_row["rule_id"]:
                rationale += " Triggered by the exact same rule."
                
            results.append({
                "batch_id": h["violation_batch_id"],
                "rule_id": h["rule_id"],
                "similarity_score": round(score * 100, 1),
                "matched_keywords": matched_keywords,
                "rationale": rationale,
                "historical_resolution": h["status"],
                "human_validated_interpretation": h["edited_summary"],
                "created_at": h["created_at"].isoformat()
            })
            
    # Sort by highest similarity
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return results[:5]
