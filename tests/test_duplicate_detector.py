import polars as pl
from app.ingestion.processors.duplicate_detector import DuplicateDetector, execute_duplicate_detection

def test_duplicate_detector_basic():
    """Verify duplicate detection correctly identifies true duplicates."""
    df = pl.DataFrame({
        "id": [1, 2, 2, 3],
        "val": ["A", "B", "B", "C"]
    })
    
    processed_df, stats = execute_duplicate_detection(df)
    
    # Assert columns injected
    assert "__row_hash" in processed_df.columns
    assert "__is_duplicate" in processed_df.columns
    
    # Valid output logic
    assert stats["total_duplicates"] == 2
    assert stats["duplicate_percentage"] == 50.0
    
    # Rows 1 and 2 (0-indexed) are duplicates of each other
    assert processed_df["__is_duplicate"].to_list() == [False, True, True, False]
    
    # Hashes for items mathematically verified identical match
    hashes = processed_df["__row_hash"].to_list()
    assert hashes[1] == hashes[2]
    assert hashes[0] != hashes[1]

def test_duplicate_detector_empty():
    """Verify behavior matches expected failovers when no data is parsed."""
    df = pl.DataFrame({"a": [], "b": []})
    processed_df, stats = execute_duplicate_detection(df)
    
    assert stats["total_duplicates"] == 0
    assert stats["duplicate_percentage"] == 0.0
    assert "__row_hash" in processed_df.columns
    assert "__is_duplicate" in processed_df.columns

def test_duplicate_detector_subset():
    """Verify that targeting only explicit columns ignores deviations in other columns."""
    df = pl.DataFrame({
        "id": [1, 2, 3],
        "val": ["A", "A", "C"]
    })
    processed_df, stats = execute_duplicate_detection(df, subset=["val"])
    
    assert stats["total_duplicates"] == 2
    # 2 out of 3 are sharing the "A" identifier
    assert stats["duplicate_percentage"] == round((2/3)*100, 2)
