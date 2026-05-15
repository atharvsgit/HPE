import json
from pathlib import Path
from typing import Dict, Any

import polars as pl
from loguru import logger


class DatasetProfiler:
    """
    Production-grade dataset profiling engine using Polars.
    Optimized for large datasets using vectorized operations.
    """

    def __init__(self, dataset_name: str, output_base_dir: str = "/data/profiling"):
        """
        Initialize the Profiler with the target dataset name.
        
        Args:
            dataset_name (str): Name of the dataset to profile.
            output_base_dir (str): Base output directory.
        """
        self.dataset_name = dataset_name
        self.output_dir = Path(output_base_dir) / dataset_name / "latest"

    def profile(self, df: pl.DataFrame) -> Dict[str, Any]:
        """
        Profiles the given DataFrame computing statistics optimally.
        
        Args:
            df (pl.DataFrame): Input dataframe.
            
        Returns:
            Dict[str, Any]: Complete dataset profile schema.
        """
        logger.info(f"Starting profiling for dataset '{self.dataset_name}' | Rows: {df.height}, Cols: {df.width}")

        profile: Dict[str, Any] = {
            "dataset_name": self.dataset_name,
            "row_count": df.height,
            "column_count": df.width,
            "columns": {}
        }

        if df.is_empty():
            logger.warning(f"Dataset '{self.dataset_name}' is empty. Returning base profile.")
            return profile

        # 1) Vectorized calculations for all columns simultaneously
        null_counts = df.null_count().to_dicts()[0]
        n_uniques = df.select(pl.all().n_unique()).to_dicts()[0]
        schema = df.schema

        # Segregate columns by data type for specific aggregations
        numeric_dt_groups = frozenset([pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64, pl.Float32, pl.Float64, pl.Decimal])
        numeric_cols = [name for name, dtype in schema.items() if dtype in numeric_dt_groups]
        string_cols = [name for name, dtype in schema.items() if dtype in (pl.Utf8, pl.Categorical, pl.String)]
        date_cols = [name for name, dtype in schema.items() if dtype in (pl.Date, pl.Datetime)]

        logger.debug(f"Detected DataTypes -> Numeric: {len(numeric_cols)}, String: {len(string_cols)}, Date: {len(date_cols)}")

        # 2) Bulk numeric statistics (vectorized matrix operation)
        numeric_stats = {}
        if numeric_cols:
            try:
                numeric_stats = df.select([
                    pl.col(numeric_cols).min().name.suffix("_min"),
                    pl.col(numeric_cols).max().name.suffix("_max"),
                    pl.col(numeric_cols).mean().name.suffix("_mean"),
                    pl.col(numeric_cols).std().name.suffix("_std"),
                    pl.col(numeric_cols).quantile(0.25).name.suffix("_p25"),
                    pl.col(numeric_cols).quantile(0.50).name.suffix("_p50"),
                    pl.col(numeric_cols).quantile(0.75).name.suffix("_p75"),
                ]).to_dicts()[0]
            except Exception as e:
                logger.error(f"Error computing numeric stats in bulk: {e}")

        # 3) Bulk date statistics (vectorized matrix operation)
        date_stats = {}
        if date_cols:
            try:
                date_stats = df.select([
                    pl.col(date_cols).min().name.suffix("_min"),
                    pl.col(date_cols).max().name.suffix("_max"),
                ]).to_dicts()[0]
            except Exception as e:
                logger.error(f"Error computing date stats in bulk: {e}")

        # Assign compiled metrics mapping back to the standard profile payload
        for col_name, dtype in schema.items():
            dt_str = str(dtype)
            nulls = null_counts.get(col_name, 0)
            
            col_profile = {
                "inferred_data_type": dt_str,
                "null_count": nulls,
                "null_percentage": round((nulls / df.height) * 100, 2) if df.height > 0 else 0.0,
                "unique_count": n_uniques.get(col_name, 0),
            }

            if col_name in numeric_cols:
                col_profile.update({
                    "min": numeric_stats.get(f"{col_name}_min"),
                    "max": numeric_stats.get(f"{col_name}_max"),
                    "mean": numeric_stats.get(f"{col_name}_mean"),
                    "std": numeric_stats.get(f"{col_name}_std"),
                    "percentiles": {
                        "25": numeric_stats.get(f"{col_name}_p25"),
                        "50": numeric_stats.get(f"{col_name}_p50"),
                        "75": numeric_stats.get(f"{col_name}_p75"),
                    }
                })

            elif col_name in date_cols:
                min_dt = date_stats.get(f"{col_name}_min")
                max_dt = date_stats.get(f"{col_name}_max")
                col_profile.update({
                    "min": str(min_dt) if min_dt is not None else None,
                    "max": str(max_dt) if max_dt is not None else None,
                })

            elif col_name in string_cols:
                try:
                    # In Polars, value_counts creates a dataframe with the column name and 'count', or returns a struct
                    vc_df = df.get_column(col_name).drop_nulls().value_counts().sort("count", descending=True).head(5)
                    top_values = {str(row[col_name]): row["count"] for row in vc_df.to_dicts()}
                    col_profile.update({"top_values": top_values})
                except Exception as e:
                    logger.warning(f"Could not compute top values for '{col_name}': {e}")
                    col_profile.update({"top_values": {}})

            profile["columns"][col_name] = col_profile

        logger.info(f"Successfully profiled dataset '{self.dataset_name}'.")
        return profile

    def save_profile(self, profile: Dict[str, Any]) -> Path:
        """
        Saves the profiling JSON to the output directory structure.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target_path = self.output_dir / "profile.json"
        
        with open(target_path, "w") as f:
            json.dump(profile, f, indent=2, default=str)
            
        logger.info(f"Profile saved to: {target_path}")
        return target_path


# ==========================================
# Helper Utilities & Example Usage
# ==========================================

def run_profiler(dataset_name: str, df: pl.DataFrame, output_base_dir: str = "/data/profiling") -> Dict[str, Any]:
    """
    Utility wrapper to instantly profile an in-memory Polars DataFrame.
    
    Args:
        dataset_name: Used for the JSON structuring.
        df: Polars DataFrame to analyze.
        output_base_dir: Mount path to place `/data/profiling/NAME/latest/profile.json`
        
    Returns:
        JSON Dict metadata.
    """
    try:
        profiler = DatasetProfiler(dataset_name=dataset_name, output_base_dir=output_base_dir)
        profile_data = profiler.profile(df)
        profiler.save_profile(profile_data)
        return profile_data
    except Exception as e:
        logger.error(f"Profiling failed for '{dataset_name}': {e}")
        raise

if __name__ == "__main__":
    # Example snippet showing direct utility invocation
    import datetime
    
    # 1. Create mock data
    example_df = pl.DataFrame({
        "id": [1, 2, 3, 4, None],
        "category": ["A", "B", "A", "C", "A"],
        "joined": [
            datetime.date(2023, 1, 1), 
            datetime.date(2023, 1, 2), 
            datetime.date(2023, 1, 3), 
            datetime.date(2023, 1, 4), 
            None
        ],
        "revenue": [10.5, 20.0, 15.5, 10.0, 50.0]
    })
    
    # 2. Run standard profiling wrapper
    # Testing mode triggers standard out logging
    logger.info("Executing profiler standalone test.")
    result = run_profiler("example_org_data", example_df, output_base_dir="./test_output")
    print(json.dumps(result, indent=2, default=str))