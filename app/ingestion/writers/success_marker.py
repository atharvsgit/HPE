"""
app/ingestion/writers/success_marker.py
=======================================
Production-grade _SUCCESS marker generator for data pipelines.
Provides atomicity to downstream consumers indicating partition readiness.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Union

from loguru import logger


class SuccessMarker:
    """
    Manages the generation of an atomic _SUCCESS indicator file containing batch metadata.
    Provides downstream tasks an atomic guarantee that a dataset partition is fully written.
    """

    def __init__(self, output_dir: Union[str, Path]):
        """
        Initialize the SuccessMarker.

        Args:
            output_dir: The directory where the _SUCCESS file will be placed. 
                        Usually alongside the partitioned Parquet files.
        """
        self.output_dir = Path(output_dir)

    def mark_success(
        self, 
        batch_id: str, 
        row_count: int, 
        schema_version: str = "1.0.0"
    ) -> Path:
        """
        Generates and writes an atomic _SUCCESS JSON marker.

        Args:
            batch_id (str): Unique identifier for the batch.
            row_count (int): Final count of records digested.
            schema_version (str): The tracked schema version.

        Returns:
            Path: The resulting absolute path to the _SUCCESS file.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        success_file_path = self.output_dir / "_SUCCESS"
        # Unique temporary target to ensure purely atomic file swaps
        temp_file_path = self.output_dir / f"_SUCCESS.{batch_id}.tmp"

        payload: Dict[str, Any] = {
            "batch_id": batch_id,
            "row_count": row_count,
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "schema_version": schema_version
        }

        try:
            # Write to a temporary file first for atomic transaction behavior
            with open(temp_file_path, "w", encoding="utf-8") as tmp_file:
                json.dump(payload, tmp_file, indent=2, default=str)
            
            # Atomic rename (POSIX, and relatively safe universally in Python 3.3+)
            temp_file_path.replace(success_file_path)
            
            logger.info(f"Successfully placed atomic _SUCCESS marker for batch '{batch_id}' at {success_file_path}")
            return success_file_path

        except Exception as e:
            logger.error(f"Failed to generate _SUCCESS marker for batch '{batch_id}': {e}")
            # Try to safely clean up the dangling temp file if any error occurred mid-write
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except Exception as cleanup_error:
                    logger.warning(f"Could not clean up temporary _SUCCESS marker logic trap: {cleanup_error}")
            raise


# ==========================================
# Helper Utilities
# ==========================================

def write_success_marker(
    output_dir: Union[str, Path],
    batch_id: str,
    row_count: int,
    schema_version: str = "1.0.0"
) -> Path:
    """
    Utility wrapper to securely instantiate and map a success marker atomically.
    
    Args:
        output_dir: Deployment directory target.
        batch_id: Unique batch job run identifier.
        row_count: Processed rows count.
        schema_version: Bound version lineage string.
        
    Returns:
        Path generated successfully.
    """
    marker = SuccessMarker(output_dir)
    return marker.mark_success(batch_id, row_count, schema_version)
