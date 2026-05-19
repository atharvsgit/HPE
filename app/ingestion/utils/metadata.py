"""
app/ingestion/utils/metadata.py
===============================
Production-grade metadata enrichment module for the Data Quality Platform.

Features
--------
- Column name normalisation (snake_case, alphanumeric).
- Metadata injection (UUID, batch ID, timestamps, source info).
- Deterministic row hashing (SHA256) ignoring metadata columns.
- Duplicate detection based on row hashes.
- Vectorised Polars operations for maximum performance.
- Loguru structured logging.
"""

from __future__ import annotations

import hashlib
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

import polars as pl
from loguru import logger

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class MetadataEnrichmentError(Exception):
    """Base exception for metadata enrichment failures."""

# ---------------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------------

_MULTI_UNDER = re.compile(r"_+")
_NON_ALNUM = re.compile(r"[^0-9a-zA-Z]+")


def to_snake_case(name: str) -> str:
    """
    Normalise an arbitrary column header to snake_case.

    Steps
    -----
    1. Strip surrounding whitespace.
    2. Replace non-alphanumeric characters with underscores.
    3. Insert underscores at camelCase/PascalCase boundaries.
    4. Collapse consecutive underscores.
    5. Lower-case the result.
    """
    name = name.strip()
    name = _NON_ALNUM.sub("_", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = _MULTI_UNDER.sub("_", name)
    return name.lower().strip("_")


def normalise_columns(df: pl.DataFrame) -> pl.DataFrame:
    """
    Rename all columns in `df` to snake_case, deduplicating clashes.
    """
    seen: dict[str, int] = {}
    new_names: list[str] = []
    for col in df.columns:
        base = to_snake_case(col)
        if base in seen:
            seen[base] += 1
            new_names.append(f"{base}_{seen[base]}")
        else:
            seen[base] = 0
            new_names.append(base)
    
    logger.debug("Normalised columns: {} -> {}", df.columns, new_names)
    return df.rename(dict(zip(df.columns, new_names)))


# ---------------------------------------------------------------------------
# Core Metadata Enrichment Class
# ---------------------------------------------------------------------------

class MetadataEnricher:
    """
    Applies standard metadata columns and row hashing to a Polars DataFrame.
    """

    def __init__(self, batch_id: str, source_name: str, source_type: str) -> None:
        """
        Initialise the enricher with batch-level metadata.

        Parameters
        ----------
        batch_id: Identifier for the ingestion batch.
        source_name: Name of the data source (e.g., "sales_db").
        source_type: Type of the source (e.g., "csv", "postgres").
        """
        self.batch_id = batch_id
        self.source_name = source_name
        self.source_type = source_type
        # Fix the timestamp for the entire batch
        self._ingested_at = datetime.now(timezone.utc)
        self._partition_date = self._ingested_at.strftime("%Y-%m-%d")

    def _generate_uuids(self, n: int) -> list[str]:
        """Generate a list of UUID strings."""
        return [str(uuid.uuid4()) for _ in range(n)]

    def _compute_row_hashes(self, df: pl.DataFrame, data_cols: list[str]) -> pl.Series:
        """
        Compute SHA256 hash for each row based on the original data columns.
        """
        if not data_cols:
            logger.warning("No data columns provided for hashing. Using empty string.")
            empty_hash = hashlib.sha256(b"").hexdigest()
            return pl.Series("__row_hash", [empty_hash] * df.height)

        # Vectorised string concatenation of all data columns
        # We fill nulls with an empty string to ensure deterministic concatenation
        # We use a unit separator (ASCII 31) to prevent collision between ("a", "bc") and ("ab", "c")
        separator = chr(31)
        
        # Build an expression that casts to string and fills nulls
        exprs = [pl.col(c).cast(pl.String).fill_null("") for c in data_cols]
        
        concat_expr = pl.concat_str(exprs, separator=separator)
        
        logger.debug("Computing SHA256 hashes for {} rows across {} columns.", df.height, len(data_cols))
        
        # We use map_elements to compute SHA256 since it's not a native expression operator.
        # This is safe and performs well for large datasets when batched correctly.
        concat_series = df.select(concat_expr).to_series()
        hash_series = concat_series.map_elements(
            lambda x: hashlib.sha256(x.encode("utf-8")).hexdigest(),
            return_dtype=pl.String
        )
        return hash_series.alias("__row_hash")

    def enrich(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Process the DataFrame:
        1. Normalise columns.
        2. Identify data columns (before adding metadata).
        3. Add static metadata columns.
        4. Add row hashes.
        5. Flag duplicates based on row hashes.

        Returns
        -------
        pl.DataFrame
            The enriched DataFrame.
        """
        t0 = datetime.now()
        logger.info("Starting metadata enrichment for batch_id='{}'", self.batch_id)

        try:
            # 1. Normalise columns
            df = normalise_columns(df)
            
            # 2. Record original data columns for hashing
            data_cols = df.columns.copy()

            # 3. Add static metadata
            df = df.with_columns(
                pl.lit(self.batch_id).alias("__batch_id"),
                pl.lit(self._ingested_at).alias("__ingested_at"),
                pl.lit(self._partition_date).alias("__partition_date"),
                pl.lit(self.source_name).alias("__source_name"),
                pl.lit(self.source_type).alias("__source_type"),
            )

            # Generate and append UUIDs
            uuids = self._generate_uuids(df.height)
            df = df.with_columns(pl.Series("__record_id", uuids))

            # 4. Compute row hashes using ONLY the original data columns
            row_hashes = self._compute_row_hashes(df, data_cols)
            df = df.with_columns(row_hashes)

            # 5. Flag duplicates based on the row hash
            # If a row hash has appeared before in this batch, it is marked as duplicate
            df = df.with_columns(
                (pl.col("__row_hash").cum_count().over("__row_hash") > 1).alias("__is_duplicate")
            )

            # Ensure metadata columns appear first
            metadata_cols = [
                "__record_id",
                "__batch_id",
                "__ingested_at",
                "__partition_date",
                "__source_name",
                "__source_type",
                "__row_hash",
                "__is_duplicate",
            ]
            
            # Combine metadata columns with the original data columns, keeping metadata first
            df = df.select(metadata_cols + data_cols)

        except Exception as e:
            logger.error("Failed to enrich metadata: {}", str(e))
            raise MetadataEnrichmentError(f"Failed to enrich metadata: {e}") from e

        duration = (datetime.now() - t0).total_seconds()
        logger.info("Enrichment complete | rows={} | elapsed={:.3f}s", df.height, duration)
        return df

# ---------------------------------------------------------------------------
# Example Usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | {message}", level="DEBUG")
    
    sample_data = {
        "First Name": ["Alice", "Bob", "Alice"],
        "Age": [30, 25, 30],
        "City Name": ["NY", "LA", "NY"]
    }
    df = pl.DataFrame(sample_data)
    
    logger.info("Original DataFrame:")
    for row in df.to_dicts():
        print(row)
        
    enricher = MetadataEnricher(batch_id="batch-001", source_name="crm", source_type="csv")
    enriched_df = enricher.enrich(df)
    
    logger.info("Enriched DataFrame:")
    for row in enriched_df.to_dicts():
        print(row)
