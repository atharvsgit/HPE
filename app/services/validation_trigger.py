"""
app/services/validation_trigger.py
==================================
Enterprise-grade Validation Trigger Service.
Responsible for asynchronously notifying the validation engine once data ingestion and profiling
have successfully completed. Includes robust retry mechanisms and circuit breaking.
"""

import asyncio
from typing import Dict, Any, Optional
import os

import httpx
from loguru import logger


class ValidationTriggerError(Exception):
    """Custom exception raised when validation trigger repeatedly fails."""
    pass


class ValidationTriggerService:
    """
    Service to asynchronously trigger downstream validation processes.
    Manages HTTP communication with the internal/external FastAPI validation endpoints,
    implementing exponential backoff and retry handling.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        timeout: float = 10.0
    ):
        """
        Initialize the ValidationTriggerService.

        Args:
            base_url: The base URL for the validation endpoints. 
                      Defaults to the `VALIDATION_API_URL` env var or localhost.
            max_retries: Number of times to retry on transient failures.
            initial_backoff: Base sleep time (in seconds) for exponential backoff.
            timeout: HTTP request timeout in seconds.
        """
        self.base_url = base_url or os.getenv("VALIDATION_API_URL", "http://localhost:8000")
        # Ensure base URL doesn't end with a slash for clean path joining
        self.base_url = self.base_url.rstrip("/")
        
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.timeout = timeout

    async def trigger_validation(
        self,
        dataset_name: str,
        batch_id: str,
        parquet_path: str,
        profile_path: str
    ) -> Dict[str, Any]:
        """
        Asynchronously triggers the validation process by calling the API endpoint.
        Uses exponential backoff for resilience against transient networking issues.

        Args:
            dataset_name (str): Identifier of the ingested dataset.
            batch_id (str): Generated UUID/String for the ingestion batch.
            parquet_path (str): URI/Path to the successfully written Parquet partition.
            profile_path (str): URI/Path to the generated dataset profile metadata.

        Returns:
            Dict[str, Any]: The response payload from the validation API.

        Raises:
            ValidationTriggerError: If the maximum number of retries is exceeded.
        """
        endpoint = f"{self.base_url}/api/v1/validation/trigger"
        
        payload = {
            "dataset_name": dataset_name,
            "batch_id": batch_id,
            "parquet_path": parquet_path,
            "profile_path": profile_path
        }

        logger.info(
            f"Preparing to trigger validation for dataset='{dataset_name}', batch_id='{batch_id}'"
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    logger.debug(f"Validation trigger attempt {attempt}/{self.max_retries} to {endpoint}")
                    
                    response = await client.post(endpoint, json=payload)
                    
                    # Raise for HTTP 4xx/5xx status codes
                    response.raise_for_status()

                    response_data = response.json()
                    logger.info(f"Successfully triggered validation for batch '{batch_id}'.")
                    
                    return response_data

                except httpx.HTTPStatusError as e:
                    # Capture HTTP specific errors (e.g., 500 Internal Server Error, 502 Bad Gateway)
                    status_code = e.response.status_code
                    logger.warning(
                        f"HTTP {status_code} received from validation endpoint on attempt {attempt}. "
                        f"Response: {e.response.text}"
                    )
                    # If it's a client error (4xx) other than 429, fail fast as retries likely won't help
                    if 400 <= status_code < 500 and status_code != 429:
                        logger.error(f"Unrecoverable client error ({status_code}) during validation trigger.")
                        raise ValidationTriggerError(f"Client error {status_code}: {e.response.text}") from e

                except (httpx.RequestError, asyncio.TimeoutError) as e:
                    # Capture connection, network, and timeout errors
                    logger.warning(f"Network error on validation trigger attempt {attempt}: {e}")

                # If this wasn't the last attempt, sleep with exponential backoff
                if attempt < self.max_retries:
                    sleep_time = self.initial_backoff * (2 ** (attempt - 1))
                    logger.debug(f"Sleeping for {sleep_time}s before retrying...")
                    await asyncio.sleep(sleep_time)

            # Exhausted all retries
            error_msg = f"Failed to trigger validation for batch '{batch_id}' after {self.max_retries} attempts."
            logger.error(error_msg)
            raise ValidationTriggerError(error_msg)


# ==========================================
# Helper Utilities
# ==========================================

async def notify_validation_engine(
    dataset_name: str,
    batch_id: str,
    parquet_path: str,
    profile_path: str,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Utility wrapper to instantly trigger the validation engine asynchronously.
    """
    service = ValidationTriggerService(base_url=base_url)
    return await service.trigger_validation(
        dataset_name=dataset_name,
        batch_id=batch_id,
        parquet_path=parquet_path,
        profile_path=profile_path
    )
