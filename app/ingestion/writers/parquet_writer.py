"""
app/ingestion/writers/parquet_writer.py
=======================================
Enterprise-grade Parquet writer service for the Data Ingestion Platform.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

import polars as pl
from loguru import logger


class ParquetWriterError(Exception):
    """Base exception for parquet writer failures."""


class ParquetWriter:
    """
    Service to write Polars DataFrames to partitioned Parquet files.
    Supports atomic writes, Snappy compression, and _SUCCESS marker generation.
    """

    def __init__(self, base_output_dir: Union[str, Path], schema_version: str = "1.0.0") -> None:
        """
        Initialises the ParquetWriter.

        Parameters
        ----------
        base_output_dir : str | Path
            The base directory where datasets will be written.
        schema_version : str
            The format or schema version of the output (default '1.0.0').
        """
        self.base_output_dir = Path(base_output_dir)
        self.schema_version = schema_version

    def write(
        self, 
        df: pl.DataFrame, 
        dataset_name: str, 
        batch_id: str, 
        partition_date: str
    ) -> Path:
        """
        Write a DataFrame to a partitioned Parquet layout.

        The output structure is:
        {base_output_dir}/{dataset_name}/partition_date={partition_date}/{batch_id}.parquet

        Writes are performed atomically via a temporary file extension (.tmp).
        Upon success, a _SUCCESS metadata marker is created in the partition directory.

        Parameters
        ----------
        df : pl.DataFrame
            The dataset to write.
        dataset_name : str
            The logical name of the dataset.
        batch_id : str
            Unique identifier for the processing batch.
        partition_date : str
            The partition date string, usually YYYY-MM-DD.

        Returns
        -------
        Path
            The filesystem path to the successfully written Parquet file.
        """
        row_count = df.height
        logger.info(
            "Writing dataset='{}' | batch_id='{}' | partition_date='{}' | rows={}",
            dataset_name, batch_id, partition_date, row_count
        )

        # 1. Ensure partition directories exist
        partition_dir = self.base_output_dir / dataset_name / f"partition_date={partition_date}"
        try:
            partition_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Failed to create partition directory '{}': {}", partition_dir, e)
            raise ParquetWriterError(f"Directory creation failed: {e}") from e

        target_file = partition_dir / f"{batch_id}.parquet"
        tmp_file = target_file.with_suffix(".parquet.tmp")

        try:
            # 2. Write DataFrame to temporary path with PyArrow & Snappy compression
            df.write_parquet(
                tmp_file,
                compression="snappy",
                use_pyarrow=True
            )

            # 3. Rename atomically back to target file
            tmp_file.replace(target_file)
            logger.debug("Successfully saved Parquet file to: {}", target_file)

        except Exception as e:
            logger.error("Error writing Parquet file: {}", e)
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            raise ParquetWriterError(f"Parquet write operation failed: {e}") from e

        # 4. Generate the _SUCCESS marker atomically
        marker_target = partition_dir / f"_SUCCESS_{batch_id}"
        marker_tmp = marker_target.with_suffix(".tmp")
        
        metadata = {
            "batch_id": batch_id,
            "row_count": row_count,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": self.schema_version,
        }

        try:
            with marker_tmp.open("w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            marker_tmp.replace(marker_target)
            logger.debug("Created success marker: {}", marker_target)
        except Exception as e:
            logger.warning("Failed to write _SUCCESS marker: {}", e)
            # Marker failure does not invalidate the data, but log a warning.

        logger.info("Batch '_{}' write completed successfully.", batch_id)
        return target_file
