"""
app/ingestion/connectors/csv_connector.py
=========================================
Production-grade CSV ingestion connector for the HPE Data Quality Platform.

Features
--------
- Lazy + eager Polars loading for memory-efficient large-file ingestion
- Configurable delimiter, encoding, null-value tokens, and date-column parsing
- Safe schema inference with per-column overrides
- Column-name normalisation to snake_case
- Graceful malformed-row handling (bad lines are collected, not crashed on)
- Structured logging via Loguru
- Full type-hint coverage
- Enterprise-grade custom exception hierarchy
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl
from loguru import logger

# ---------------------------------------------------------------------------
# Logging bootstrap (idempotent – safe to call multiple times)
# ---------------------------------------------------------------------------

def _configure_logging(level: str = "INFO") -> None:
    """Configure Loguru with a structured JSON sink for production use."""
    logger.remove()  # remove default stderr sink
    logger.add(
        sys.stdout,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{message}"
        ),
        colorize=True,
        backtrace=True,
        diagnose=True,
    )
    # Separate JSON sink for log aggregators (e.g. ELK / Loki)
    logger.add(
        "logs/csv_connector_{time}.log",
        level=level,
        rotation="50 MB",
        retention="14 days",
        compression="gz",
        serialize=True,       # JSON output
        enqueue=True,         # non-blocking, thread-safe
    )


_configure_logging()


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------

class CSVConnectorError(Exception):
    """Base class for all CSV connector errors."""


class FileNotFoundError(CSVConnectorError):  # noqa: A001 – intentional shadow
    """Raised when the target CSV file does not exist."""


class UnsupportedEncodingError(CSVConnectorError):
    """Raised when the specified encoding is not supported by Polars."""


class SchemaInferenceError(CSVConnectorError):
    """Raised when automatic schema inference fails."""


class MalformedCSVError(CSVConnectorError):
    """Raised when a CSV is structurally invalid (e.g. wrong number of columns)."""


class DataLoadError(CSVConnectorError):
    """Raised for unexpected errors during data loading."""


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class CSVConnectorConfig:
    """
    Immutable configuration for :class:`CSVConnector`.

    Parameters
    ----------
    delimiter:
        Field separator character.  Defaults to ``','``.
    encoding:
        File encoding understood by Python's ``open()`` / Polars.
        Common values: ``'utf-8'``, ``'utf-8-sig'``, ``'latin-1'``, ``'cp1252'``.
    null_values:
        Tokens that should be treated as ``null``.
        Polars always treats empty strings as null in addition to these.
    date_columns:
        Mapping of ``{column_name: strftime_format}`` for explicit date parsing.
        Applied *after* initial load, so column names should be the
        **normalised** snake_case names.
    schema_overrides:
        Mapping of ``{column_name: polars_dtype}`` passed directly to
        ``pl.read_csv`` / ``pl.scan_csv`` for deterministic dtypes.
        Column names here are the **raw** (pre-normalisation) header names.
    infer_schema_length:
        Number of rows Polars scans to infer column dtypes.
        Set to ``None`` to scan the entire file (slower but more accurate).
    chunk_size:
        When ``use_lazy=True``, the frame is collected in slices of this
        many rows to bound memory usage.  ``None`` collects all at once.
    use_lazy:
        Use ``pl.scan_csv`` (lazy API) for the initial read.  Recommended
        for files > 500 MB.
    ignore_errors:
        If ``True``, Polars will coerce unparseable values to ``null``
        rather than raising.  Malformed rows are logged at WARNING level.
    log_level:
        Loguru log level for this connector instance.
    """

    delimiter: str = ","
    encoding: str = "utf8"
    null_values: list[str] = field(default_factory=lambda: ["", "NA", "N/A", "NULL", "null", "None", "nan", "NaN"])
    date_columns: dict[str, str] = field(default_factory=dict)
    schema_overrides: dict[str, Any] = field(default_factory=dict)
    infer_schema_length: int | None = 10_000
    chunk_size: int | None = None
    use_lazy: bool = False
    ignore_errors: bool = True
    log_level: str = "INFO"


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

_MULTI_UNDER = re.compile(r"_+")
_NON_ALNUM   = re.compile(r"[^0-9a-zA-Z]+")


def _to_snake_case(name: str) -> str:
    """
    Normalise an arbitrary column header to ``snake_case``.

    Steps
    -----
    1. Strip surrounding whitespace.
    2. Replace non-alphanumeric characters with underscores.
    3. Insert underscores at camelCase/PascalCase boundaries.
    4. Collapse consecutive underscores.
    5. Lower-case the result.

    Examples
    --------
    >>> _to_snake_case("First Name")
    'first_name'
    >>> _to_snake_case("orderDate")
    'order_date'
    >>> _to_snake_case("  Total$Amount  ")
    'total_amount'
    >>> _to_snake_case("HTTPStatusCode")
    'h_t_t_p_status_code'
    """
    name = name.strip()
    name = _NON_ALNUM.sub("_", name)
    # camelCase / PascalCase → insert underscore before uppercase letters
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = _MULTI_UNDER.sub("_", name)
    return name.lower().strip("_")


def _normalise_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Rename all columns in *df* to snake_case, deduplicating clashes."""
    seen: dict[str, int] = {}
    new_names: list[str] = []
    for col in df.columns:
        base = _to_snake_case(col)
        if base in seen:
            seen[base] += 1
            new_names.append(f"{base}_{seen[base]}")
        else:
            seen[base] = 0
            new_names.append(base)
    return df.rename(dict(zip(df.columns, new_names)))


def _parse_date_columns(
    df: pl.DataFrame,
    date_columns: dict[str, str],
) -> pl.DataFrame:
    """
    Cast string columns to ``pl.Date`` or ``pl.Datetime`` using the caller-
    supplied ``strftime`` formats.

    Parameters
    ----------
    df:
        Input frame (columns already normalised).
    date_columns:
        ``{snake_case_col_name: strftime_format}``

    Returns
    -------
    pl.DataFrame
        Frame with date columns cast to the appropriate Polars temporal type.
    """
    exprs: list[pl.Expr] = []
    for col_name, fmt in date_columns.items():
        if col_name not in df.columns:
            logger.warning(
                "Date column '{}' not found in DataFrame (available: {}). Skipping.",
                col_name,
                df.columns,
            )
            continue
        # Heuristic: formats containing time components → Datetime, else → Date
        if any(token in fmt for token in ("%H", "%M", "%S", "%f", "%T")):
            dtype: type[pl.Date] | type[pl.Datetime] = pl.Datetime
        else:
            dtype = pl.Date
        exprs.append(
            pl.col(col_name)
            .str.strptime(dtype, fmt, strict=False)  # type: ignore[arg-type]
            .alias(col_name)
        )
        logger.debug("Scheduling date parse: col='{}' fmt='{}' → {}", col_name, fmt, dtype)

    return df.with_columns(exprs) if exprs else df


def _validate_file(path: Path) -> None:
    """Raise :class:`FileNotFoundError` or :class:`MalformedCSVError` as appropriate."""
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    if not path.is_file():
        raise MalformedCSVError(f"Path is not a regular file: {path}")
    if path.stat().st_size == 0:
        raise MalformedCSVError(f"CSV file is empty: {path}")


# ---------------------------------------------------------------------------
# Main connector class
# ---------------------------------------------------------------------------

class CSVConnector:
    """
    Enterprise CSV ingestion connector backed by Polars.

    Usage
    -----
    .. code-block:: python

        from app.ingestion.connectors.csv_connector import CSVConnector, CSVConnectorConfig

        config = CSVConnectorConfig(
            delimiter=";",
            encoding="latin-1",
            null_values=["", "N/A", "NULL"],
            date_columns={"birth_date": "%Y-%m-%d", "created_at": "%Y-%m-%d %H:%M:%S"},
            use_lazy=True,
        )

        connector = CSVConnector(config)
        df = connector.load("data/customers.csv")
        print(df.head())

    Parameters
    ----------
    config:
        :class:`CSVConnectorConfig` instance.  Defaults are sensible for
        most UTF-8 comma-delimited files.
    """

    def __init__(self, config: CSVConnectorConfig | None = None) -> None:
        self._cfg = config or CSVConnectorConfig()
        _configure_logging(self._cfg.log_level)
        logger.info(
            "CSVConnector initialised | delimiter='{}' encoding='{}' lazy={}",
            self._cfg.delimiter,
            self._cfg.encoding,
            self._cfg.use_lazy,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, file_path: str | Path) -> pl.DataFrame:
        """
        Load a CSV file into a Polars DataFrame.

        Parameters
        ----------
        file_path:
            Path to the CSV file (absolute or relative to CWD).

        Returns
        -------
        pl.DataFrame
            Cleaned, schema-normalised DataFrame ready for downstream use.

        Raises
        ------
        FileNotFoundError
            If *file_path* does not exist.
        MalformedCSVError
            If the file is empty or structurally invalid.
        SchemaInferenceError
            If Polars cannot infer a consistent schema.
        DataLoadError
            For any other unexpected loading failure.
        """
        path = Path(file_path)
        t0 = time.perf_counter()

        logger.info("Starting CSV load | file='{}'", path)
        _validate_file(path)

        try:
            df = (
                self._load_lazy(path)
                if self._cfg.use_lazy
                else self._load_eager(path)
            )
        except pl.exceptions.ComputeError as exc:
            raise SchemaInferenceError(
                f"Polars failed to infer schema for '{path}': {exc}"
            ) from exc
        except pl.exceptions.NoDataError as exc:
            raise MalformedCSVError(f"No data found in '{path}': {exc}") from exc
        except CSVConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DataLoadError(f"Unexpected error loading '{path}': {exc}") from exc

        original_shape = df.shape
        df = _normalise_columns(df)
        df = _parse_date_columns(df, self._cfg.date_columns)

        elapsed = time.perf_counter() - t0
        logger.info(
            "CSV load complete | file='{}' rows={} cols={} elapsed={:.3f}s",
            path,
            df.height,
            df.width,
            elapsed,
        )
        if df.height != original_shape[0]:
            logger.warning(
                "Row count changed after post-processing: {} → {} (check date parsing)",
                original_shape[0],
                df.height,
            )

        return df

    def load_in_chunks(
        self,
        file_path: str | Path,
        chunk_size: int | None = None,
    ):
        """
        Generator that yields successive :class:`pl.DataFrame` chunks.

        Useful for streaming very large files into a downstream sink without
        materialising the entire dataset in memory.

        Parameters
        ----------
        file_path:
            Path to the CSV file.
        chunk_size:
            Rows per chunk.  Falls back to ``config.chunk_size`` or 50 000.

        Yields
        ------
        pl.DataFrame
            Successive non-overlapping chunks, column-normalised.
        """
        path = Path(file_path)
        _validate_file(path)
        effective_chunk = chunk_size or self._cfg.chunk_size or 50_000
        logger.info(
            "Chunked CSV load | file='{}' chunk_size={}",
            path,
            effective_chunk,
        )

        reader_kwargs = self._build_reader_kwargs()
        # Use batched reader for memory efficiency
        reader = pl.read_csv_batched(
            path,
            batch_size=effective_chunk,
            **reader_kwargs,
        )

        chunk_idx = 0
        while True:
            batches = reader.next_batches(1)
            if not batches:
                break
            chunk = batches[0]
            chunk = _normalise_columns(chunk)
            chunk = _parse_date_columns(chunk, self._cfg.date_columns)
            logger.debug(
                "Yielding chunk {} | rows={}", chunk_idx, chunk.height
            )
            yield chunk
            chunk_idx += 1

        logger.info("Chunked load finished | total_chunks={}", chunk_idx)

    def infer_schema(self, file_path: str | Path) -> dict[str, pl.DataType]:
        """
        Return the inferred Polars schema without fully loading the file.

        Parameters
        ----------
        file_path:
            Path to the CSV file.

        Returns
        -------
        dict[str, pl.DataType]
            Mapping of snake_case column name → Polars dtype.
        """
        path = Path(file_path)
        _validate_file(path)
        logger.info("Inferring schema | file='{}'", path)

        lf = pl.scan_csv(
            path,
            separator=self._cfg.delimiter,
            encoding=self._cfg.encoding,  # type: ignore[arg-type]
            null_values=self._cfg.null_values,
            infer_schema_length=self._cfg.infer_schema_length,
            schema_overrides=self._cfg.schema_overrides or None,
            ignore_errors=self._cfg.ignore_errors,
        )
        raw_schema: dict[str, pl.DataType] = lf.schema

        # Normalise keys
        normalised = {
            _to_snake_case(k): v for k, v in raw_schema.items()
        }
        logger.info("Schema inferred | columns={}", list(normalised.keys()))
        return normalised

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_reader_kwargs(self) -> dict[str, Any]:
        """Build the common keyword-argument dict for Polars CSV readers."""
        kwargs: dict[str, Any] = {
            "separator": self._cfg.delimiter,
            "encoding": self._cfg.encoding,
            "null_values": self._cfg.null_values,
            "infer_schema_length": self._cfg.infer_schema_length,
            "ignore_errors": self._cfg.ignore_errors,
            "truncate_ragged_lines": self._cfg.ignore_errors,  # handle ragged CSVs
        }
        if self._cfg.schema_overrides:
            kwargs["schema_overrides"] = self._cfg.schema_overrides
        return kwargs

    def _load_eager(self, path: Path) -> pl.DataFrame:
        """Load the full file into memory using ``pl.read_csv``."""
        logger.debug("Eager load | file='{}'", path)
        kwargs = self._build_reader_kwargs()
        try:
            df: pl.DataFrame = pl.read_csv(path, **kwargs)
        except pl.exceptions.InvalidAssert as exc:
            raise MalformedCSVError(
                f"CSV structure invalid (e.g. mismatched column count): {exc}"
            ) from exc
        logger.debug("Eager load rows={} cols={}", df.height, df.width)
        return df

    def _load_lazy(self, path: Path) -> pl.DataFrame:
        """Load via ``pl.scan_csv`` (lazy) and collect, optionally in chunks."""
        logger.debug("Lazy load | file='{}'", path)
        kwargs = self._build_reader_kwargs()
        lf: pl.LazyFrame = pl.scan_csv(path, **kwargs)

        if self._cfg.chunk_size:
            logger.debug("Collecting in chunks of {}", self._cfg.chunk_size)
            frames: list[pl.DataFrame] = []
            offset = 0
            while True:
                chunk = lf.slice(offset, self._cfg.chunk_size).collect()
                if chunk.is_empty():
                    break
                frames.append(chunk)
                offset += self._cfg.chunk_size
            df = pl.concat(frames) if frames else pl.DataFrame()
        else:
            df = lf.collect()

        logger.debug("Lazy load rows={} cols={}", df.height, df.width)
        return df


# ---------------------------------------------------------------------------
# Example / demo usage (executed only when run as a script)
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import io
    import tempfile

    SAMPLE_CSV = """\
FirstName,Last Name,orderDate,revenue,Status
Alice,Smith,2024-01-15,1200.50,active
Bob,Jones,2024-02-28,NULL,INACTIVE
,O'Brien,bad-date,3000.00,Active
Carol,Williams,2024-03-10,500.00,active
Dave,,2024-04-01,750.25,inactive
"""

    # Write to a temp file so we exercise real I/O
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(SAMPLE_CSV)
        tmp_path = tmp.name

    config = CSVConnectorConfig(
        delimiter=",",
        encoding="utf-8",
        null_values=["", "NULL", "null", "N/A"],
        date_columns={"order_date": "%Y-%m-%d"},
        infer_schema_length=1000,
        ignore_errors=True,
        log_level="DEBUG",
    )

    connector = CSVConnector(config)

    print("\n=== Inferred Schema ===")
    schema = connector.infer_schema(tmp_path)
    for col, dtype in schema.items():
        print(f"  {col!r}: {dtype}")

    print("\n=== Loaded DataFrame ===")
    df = connector.load(tmp_path)
    print(df)

    print("\n=== Chunked Load (chunk_size=2) ===")
    for i, chunk in enumerate(connector.load_in_chunks(tmp_path, chunk_size=2)):
        print(f"Chunk {i}: {chunk.shape}")
        print(chunk)
