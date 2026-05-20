"""
tests/test_csv_connector.py
============================
Unit tests for :class:`app.ingestion.connectors.csv_connector.CSVConnector`.

Covers
------
- Happy-path loading (eager & lazy)
- Column name normalisation (_to_snake_case)
- Delimiter / encoding / null-value handling
- Date-column parsing (Date & Datetime)
- Schema inference
- Chunked load (load_in_chunks)
- All custom exception branches
- Empty file / missing file / directory path guards
- Duplicate column-name deduplication
- Schema overrides
- Ragged (malformed) row tolerance
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from pathlib import Path
from typing import Generator

import polars as pl
import pytest

from app.ingestion.connectors.csv_connector import (
    CSVConnector,
    CSVConnectorConfig,
    DataLoadError,
    FileNotFoundError,
    MalformedCSVError,
    SchemaInferenceError,
    UnsupportedEncodingError,
    _normalise_columns,
    _parse_date_columns,
    _to_snake_case,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_csv(tmp_path: Path):
    """Factory fixture – returns a helper that writes content to a temp CSV."""

    def _make(content: str, filename: str = "test.csv", encoding: str = "utf-8") -> Path:
        p = tmp_path / filename
        p.write_text(content, encoding=encoding)
        return p

    return _make


@pytest.fixture()
def default_connector() -> CSVConnector:
    return CSVConnector(CSVConnectorConfig(log_level="WARNING"))


# ---------------------------------------------------------------------------
# _to_snake_case unit tests
# ---------------------------------------------------------------------------

class TestToSnakeCase:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("FirstName",         "first_name"),
            ("Last Name",         "last_name"),
            ("orderDate",         "order_date"),
            ("  Total$Amount  ",  "total_amount"),
            ("alreadysnake",      "alreadysnake"),
            ("A",                 "a"),
            ("__leading",         "leading"),
            ("trailing__",        "trailing"),
            ("123NumericStart",   "123_numeric_start"),
            ("Mix-Of_Styles",     "mix_of_styles"),
            ("camelCaseColumn",   "camel_case_column"),
            ("PascalCaseColumn",  "pascal_case_column"),
            ("column__name",      "column_name"),
        ],
    )
    def test_snake_case_conversion(self, raw: str, expected: str) -> None:
        assert _to_snake_case(raw) == expected


# ---------------------------------------------------------------------------
# _normalise_columns unit tests
# ---------------------------------------------------------------------------

class TestNormaliseColumns:
    def test_basic_rename(self) -> None:
        df = pl.DataFrame({"First Name": [1], "orderDate": [2]})
        result = _normalise_columns(df)
        assert result.columns == ["first_name", "order_date"]

    def test_duplicate_deduplication(self) -> None:
        # Two columns that both normalise to "name"
        df = pl.DataFrame({"Name": [1], "name": [2]})
        result = _normalise_columns(df)
        assert "name" in result.columns
        assert "name_1" in result.columns
        assert len(result.columns) == 2


# ---------------------------------------------------------------------------
# _parse_date_columns unit tests
# ---------------------------------------------------------------------------

class TestParseDateColumns:
    def test_date_column_parsed(self) -> None:
        df = pl.DataFrame({"birth_date": ["2024-01-15", "2024-06-30"]})
        result = _parse_date_columns(df, {"birth_date": "%Y-%m-%d"})
        assert result["birth_date"].dtype == pl.Date

    def test_datetime_column_parsed(self) -> None:
        df = pl.DataFrame({"created_at": ["2024-01-15 10:30:00", "2024-06-30 23:59:59"]})
        result = _parse_date_columns(df, {"created_at": "%Y-%m-%d %H:%M:%S"})
        assert result["created_at"].dtype == pl.Datetime

    def test_missing_column_skipped(self) -> None:
        df = pl.DataFrame({"other_col": ["2024-01-15"]})
        # Should not raise – just log a warning
        result = _parse_date_columns(df, {"nonexistent": "%Y-%m-%d"})
        assert result.columns == ["other_col"]

    def test_empty_date_columns_dict(self) -> None:
        df = pl.DataFrame({"col": ["val"]})
        result = _parse_date_columns(df, {})
        assert result.equals(df)


# ---------------------------------------------------------------------------
# CSVConnector.load – happy path
# ---------------------------------------------------------------------------

SIMPLE_CSV = """\
FirstName,Last Name,Age,Revenue
Alice,Smith,30,1200.50
Bob,Jones,25,NULL
Carol,Williams,35,500.00
"""


class TestCSVConnectorLoadHappyPath:
    def test_eager_load_returns_dataframe(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        df = default_connector.load(path)
        assert isinstance(df, pl.DataFrame)

    def test_row_count(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        df = default_connector.load(path)
        assert df.height == 3

    def test_column_count(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        df = default_connector.load(path)
        assert df.width == 4

    def test_columns_are_snake_case(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        df = default_connector.load(path)
        assert df.columns == ["first_name", "last_name", "age", "revenue"]

    def test_null_values_resolved(self, tmp_csv) -> None:
        cfg = CSVConnectorConfig(null_values=["NULL"], log_level="WARNING")
        connector = CSVConnector(cfg)
        path = tmp_csv(SIMPLE_CSV)
        df = connector.load(path)
        assert df["revenue"].null_count() == 1

    def test_lazy_load_same_result(self, tmp_csv) -> None:
        path = tmp_csv(SIMPLE_CSV)
        eager_df = CSVConnector(CSVConnectorConfig(use_lazy=False, log_level="WARNING")).load(path)
        lazy_df  = CSVConnector(CSVConnectorConfig(use_lazy=True,  log_level="WARNING")).load(path)
        assert eager_df.equals(lazy_df)

    def test_accepts_pathlib_path(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        df = default_connector.load(path)  # Path object
        assert df.height == 3

    def test_accepts_string_path(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        df = default_connector.load(str(path))  # string
        assert df.height == 3


# ---------------------------------------------------------------------------
# CSVConnector.load – delimiter & encoding
# ---------------------------------------------------------------------------

SEMI_CSV = """\
FirstName;Age;Score
Alice;30;9.5
Bob;25;8.0
"""

LATIN1_CSV = "Name,City\nJos\xe9,M\xe9xico\n"  # bytes with latin-1 chars


class TestDelimiterAndEncoding:
    def test_semicolon_delimiter(self, tmp_csv) -> None:
        path = tmp_csv(SEMI_CSV)
        cfg = CSVConnectorConfig(delimiter=";", log_level="WARNING")
        df = CSVConnector(cfg).load(path)
        assert df.width == 3
        assert "first_name" in df.columns

    def test_tab_delimiter(self, tmp_path) -> None:
        content = "col_a\tcol_b\n1\t2\n3\t4\n"
        p = tmp_path / "tabs.csv"
        p.write_text(content, encoding="utf-8")
        cfg = CSVConnectorConfig(delimiter="\t", log_level="WARNING")
        df = CSVConnector(cfg).load(p)
        assert df.columns == ["col_a", "col_b"]
        assert df.height == 2

    def test_latin1_encoding(self, tmp_path) -> None:
        p = tmp_path / "latin1.csv"
        p.write_bytes(LATIN1_CSV.encode("latin-1"))
        cfg = CSVConnectorConfig(encoding="latin-1", log_level="WARNING")
        df = CSVConnector(cfg).load(p)
        assert df.height == 1
        assert "jos" in df["name"][0].lower()

    def test_utf8_bom_encoding(self, tmp_path) -> None:
        content = "name,value\nalice,1\n"
        p = tmp_path / "bom.csv"
        p.write_text(content, encoding="utf-8-sig")
        cfg = CSVConnectorConfig(encoding="utf-8-sig", log_level="WARNING")
        df = CSVConnector(cfg).load(p)
        assert "name" in df.columns


# ---------------------------------------------------------------------------
# CSVConnector.load – date parsing
# ---------------------------------------------------------------------------

DATE_CSV = """\
id,birth_date,created_at
1,2000-06-15,2024-01-01 08:00:00
2,1995-11-30,2024-06-15 23:59:59
"""


class TestDateParsing:
    def _connector_with_dates(self) -> CSVConnector:
        cfg = CSVConnectorConfig(
            date_columns={
                "birth_date": "%Y-%m-%d",
                "created_at": "%Y-%m-%d %H:%M:%S",
            },
            log_level="WARNING",
        )
        return CSVConnector(cfg)

    def test_date_column_dtype(self, tmp_csv) -> None:
        path = tmp_csv(DATE_CSV)
        df = self._connector_with_dates().load(path)
        assert df["birth_date"].dtype == pl.Date

    def test_datetime_column_dtype(self, tmp_csv) -> None:
        path = tmp_csv(DATE_CSV)
        df = self._connector_with_dates().load(path)
        assert df["created_at"].dtype == pl.Datetime

    def test_no_nulls_after_parse(self, tmp_csv) -> None:
        path = tmp_csv(DATE_CSV)
        df = self._connector_with_dates().load(path)
        assert df["birth_date"].null_count() == 0
        assert df["created_at"].null_count() == 0

    def test_bad_dates_become_null_not_crash(self, tmp_csv) -> None:
        bad = "id,birth_date\n1,not-a-date\n2,2024-01-01\n"
        path = tmp_csv(bad)
        cfg = CSVConnectorConfig(
            date_columns={"birth_date": "%Y-%m-%d"},
            ignore_errors=True,
            log_level="WARNING",
        )
        df = CSVConnector(cfg).load(path)
        # row 1 should be null; row 2 should parse correctly
        assert df["birth_date"].null_count() == 1
        assert df["birth_date"][1] is not None


# ---------------------------------------------------------------------------
# CSVConnector.load – null-value handling
# ---------------------------------------------------------------------------

class TestNullValues:
    @pytest.mark.parametrize("token", ["NA", "N/A", "NULL", "null", "None", "nan", "NaN", ""])
    def test_custom_null_tokens(self, tmp_csv, token: str) -> None:
        content = f"col_a,col_b\n{token},1\nok,2\n"
        path = tmp_csv(content)
        cfg = CSVConnectorConfig(null_values=[token], log_level="WARNING")
        df = CSVConnector(cfg).load(path)
        assert df["col_a"].null_count() >= 1


# ---------------------------------------------------------------------------
# CSVConnector.load – schema overrides
# ---------------------------------------------------------------------------

class TestSchemaOverrides:
    def test_force_string_dtype(self, tmp_csv) -> None:
        content = "id,value\n1,100\n2,200\n"
        path = tmp_csv(content)
        cfg = CSVConnectorConfig(
            schema_overrides={"id": pl.Utf8},
            log_level="WARNING",
        )
        df = CSVConnector(cfg).load(path)
        assert df["id"].dtype in (pl.Utf8, pl.String)


# ---------------------------------------------------------------------------
# CSVConnector.infer_schema
# ---------------------------------------------------------------------------

class TestInferSchema:
    def test_returns_dict(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        schema = default_connector.infer_schema(path)
        assert isinstance(schema, dict)

    def test_snake_case_keys(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        schema = default_connector.infer_schema(path)
        for key in schema:
            assert key == _to_snake_case(key), f"Key not snake_case: {key!r}"

    def test_contains_expected_columns(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        schema = default_connector.infer_schema(path)
        assert "first_name" in schema
        assert "revenue" in schema


# ---------------------------------------------------------------------------
# CSVConnector.load_in_chunks
# ---------------------------------------------------------------------------

class TestLoadInChunks:
    def test_yields_dataframes(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        chunks = list(default_connector.load_in_chunks(path, chunk_size=2))
        assert all(isinstance(c, pl.DataFrame) for c in chunks)

    def test_total_rows_match(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        chunks = list(default_connector.load_in_chunks(path, chunk_size=2))
        total = sum(c.height for c in chunks)
        assert total == 3  # SIMPLE_CSV has 3 data rows

    def test_chunk_columns_normalised(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        for chunk in default_connector.load_in_chunks(path, chunk_size=10):
            assert chunk.columns == ["first_name", "last_name", "age", "revenue"]

    def test_chunk_size_respected(self, tmp_csv, default_connector) -> None:
        path = tmp_csv(SIMPLE_CSV)
        chunks = list(default_connector.load_in_chunks(path, chunk_size=1))
        # 3 rows → 3 chunks of size 1
        assert all(c.height == 1 for c in chunks)
        assert len(chunks) == 3


# ---------------------------------------------------------------------------
# Error-handling branches
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_missing_file_raises(self, default_connector) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            default_connector.load("/nonexistent/path/file.csv")

    def test_directory_path_raises(self, tmp_path, default_connector) -> None:
        with pytest.raises(MalformedCSVError, match="not a regular file"):
            default_connector.load(tmp_path)

    def test_empty_file_raises(self, tmp_csv, default_connector) -> None:
        path = tmp_csv("")
        with pytest.raises(MalformedCSVError, match="empty"):
            default_connector.load(path)

    def test_infer_schema_missing_file(self, default_connector) -> None:
        with pytest.raises(FileNotFoundError):
            default_connector.infer_schema("/no/such/file.csv")

    def test_load_in_chunks_missing_file(self, default_connector) -> None:
        with pytest.raises(FileNotFoundError):
            list(default_connector.load_in_chunks("/no/such/file.csv"))

    def test_ragged_rows_tolerated_when_ignore_errors(self, tmp_csv) -> None:
        """A row with too few/many fields should NOT raise when ignore_errors=True."""
        ragged = "col_a,col_b,col_c\n1,2,3\n4,5\n6,7,8\n"  # row 2 is short
        path = tmp_csv(ragged)
        cfg = CSVConnectorConfig(ignore_errors=True, log_level="WARNING")
        df = CSVConnector(cfg).load(path)
        # At least the well-formed rows should be present
        assert df.height >= 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_column_csv(self, tmp_csv, default_connector) -> None:
        content = "Value\n1\n2\n3\n"
        path = tmp_csv(content)
        df = default_connector.load(path)
        assert df.width == 1
        assert df.height == 3

    def test_all_nulls_column(self, tmp_csv) -> None:
        content = "col_a,col_b\nNULL,1\nNULL,2\n"
        path = tmp_csv(content)
        cfg = CSVConnectorConfig(null_values=["NULL"], log_level="WARNING")
        df = CSVConnector(cfg).load(path)
        assert df["col_a"].null_count() == 2

    def test_very_wide_csv(self, tmp_path) -> None:
        """Connector should handle wide files (many columns) without issues."""
        n_cols = 200
        header = ",".join(f"Col{i}" for i in range(n_cols))
        row    = ",".join(str(i) for i in range(n_cols))
        content = f"{header}\n{row}\n"
        p = tmp_path / "wide.csv"
        p.write_text(content, encoding="utf-8")
        df = CSVConnector(CSVConnectorConfig(log_level="WARNING")).load(p)
        assert df.width == n_cols

    def test_lazy_chunked_load(self, tmp_csv) -> None:
        """Lazy mode with chunk_size should produce same result as eager."""
        path = tmp_csv(SIMPLE_CSV)
        eager = CSVConnector(CSVConnectorConfig(use_lazy=False, log_level="WARNING")).load(path)
        lazy  = CSVConnector(CSVConnectorConfig(use_lazy=True, chunk_size=2, log_level="WARNING")).load(path)
        assert eager.equals(lazy)

    def test_default_config_instantiation(self) -> None:
        """CSVConnector() with no arguments should not raise."""
        connector = CSVConnector()
        assert connector is not None

    def test_numeric_column_names(self, tmp_path) -> None:
        content = "123,456\nval1,val2\n"
        p = tmp_path / "nums.csv"
        p.write_text(content, encoding="utf-8")
        df = CSVConnector(CSVConnectorConfig(log_level="WARNING")).load(p)
        # Columns normalised – should start with digit or underscore
        for col in df.columns:
            assert re.match(r"^[a-z0-9_]+$", col), f"Bad column: {col}"

    def test_windows_line_endings(self, tmp_path) -> None:
        content = "name,age\r\nAlice,30\r\nBob,25\r\n"
        p = tmp_path / "crlf.csv"
        p.write_bytes(content.encode("utf-8"))
        df = CSVConnector(CSVConnectorConfig(log_level="WARNING")).load(p)
        assert df.height == 2


import re  # noqa: E402  (used in test_numeric_column_names above)
