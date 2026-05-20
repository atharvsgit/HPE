"""
app/ingestion/processors/duplicate_detector.py
==============================================
Production-grade Duplicate Detection Processor using Polars.
"""

from typing import Tuple, Dict, Any, List, Optional
import polars as pl
from loguru import logger


class DuplicateDetectionError(Exception):
    """Base exception for duplicate detection failures."""


class DuplicateDetector:
    """
    Production-grade dataset duplicate detection engine.
    Utilizes Polars vectorized hashing and evaluation for performance on massive datasets.
    """

    def __init__(self, subset: Optional[List[str]] = None) -> None:
        """
        Initialize the DuplicateDetector.

        Args:
            subset (List[str], optional): Specify a subset of columns to consider when 
                                          detecting duplicates. If None, considers all.
        """
        self.subset = subset

    def process(self, df: pl.DataFrame) -> Tuple[pl.DataFrame, Dict[str, Any]]:
        """
        Process the DataFrame to identify duplicates, append metadata columns, 
        and generate summary statistics.

        Appends to DataFrame:
            __row_hash: A deterministic hash of the feature fields.
            __is_duplicate: Boolean flag denoting if the record appears multiple times.

        Args:
            df (pl.DataFrame): Input dataframe.

        Returns:
            Tuple[pl.DataFrame, Dict[str, Any]]: The transformed dataframe and processing stats.
        """
        logger.info(f"Starting duplicate detection on dataset with {df.height} rows.")

        if df.is_empty():
            logger.warning("Empty dataframe provided to DuplicateDetector. Bypassing detection.")
            # Map default columns for empty schema consistency
            empty_df = df.with_columns([
                pl.lit(None).cast(pl.UInt64).alias("__row_hash"),
                pl.lit(False).alias("__is_duplicate")
            ])
            return empty_df, {"total_duplicates": 0, "duplicate_percentage": 0.0}

        # Select columns to hash (ignore internal pipeline columns if running recursively)
        hash_cols = self.subset if self.subset is not None else df.columns
        hash_cols = [c for c in hash_cols if c not in ("__row_hash", "__is_duplicate")]

        if not hash_cols:
            logger.warning("No valid columns to hash. All records marked non-duplicate.")
            df_out = df.with_columns([
                pl.lit(0).cast(pl.UInt64).alias("__row_hash"),
                pl.lit(False).alias("__is_duplicate")
            ])
            return df_out, {"total_duplicates": 0, "duplicate_percentage": 0.0}

        try:
            # 1. Compute Hash Vectorially across defined columns
            # 2. Flag Duplicates
            df_processed = df.with_columns(
                pl.struct(hash_cols).hash().alias("__row_hash")
            ).with_columns(
                pl.col("__row_hash").is_duplicated().alias("__is_duplicate")
            )

            # Polars' builtin boolean sum returns total True matches directly
            total_duplicates = df_processed.get_column("__is_duplicate").sum()
            duplicate_percentage = (total_duplicates / df_processed.height) * 100.0

            stats = {
                "total_duplicates": total_duplicates,
                "duplicate_percentage": round(duplicate_percentage, 2)
            }

            logger.info(f"Duplicate detection complete. Found {total_duplicates} items flagged as duplicate ({stats['duplicate_percentage']}%).")
            
            return df_processed, stats

        except Exception as e:
            logger.error(f"Duplicate validation failed: {e}")
            raise


# ==========================================
# Helper Utilities
# ==========================================

def execute_duplicate_detection(df: pl.DataFrame, subset: Optional[List[str]] = None) -> Tuple[pl.DataFrame, Dict[str, Any]]:
    """
    Utility wrapper to instantly evaluate an in-memory Polars DataFrame for duplicates.

    Args:
        df: Polars DataFrame to analyze.
        subset: (Optional) List of specific column names to check for duplicates across.

    Returns:
        Tuple containing the processed dataframe (with `__row_hash` and `__is_duplicate`) 
        and the duplicate metric statistics.
    """
    detector = DuplicateDetector(subset)
    return detector.process(df)
