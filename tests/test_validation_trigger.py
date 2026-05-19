import pytest
import httpx
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.validation_trigger import ValidationTriggerService, ValidationTriggerError


def _make_http_status_error(status_code: int, text: str = "") -> httpx.HTTPStatusError:
    """Helper to build an httpx.HTTPStatusError for a given status code."""
    request = httpx.Request("POST", "http://fake-api/api/v1/validation/trigger")
    response = httpx.Response(status_code=status_code, text=text, request=request)
    return httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=response)


@pytest.mark.asyncio
async def test_trigger_validation_success():
    """Test standard successful HTTP trigger."""
    service = ValidationTriggerService(base_url="http://fake-api")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mocked_post:
        # Construct synchronous mock inside the async wrapper
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"status": "processing"}
        mocked_post.return_value = mock_response

        result = await service.trigger_validation(
            dataset_name="sales_data",
            batch_id="b_123",
            parquet_path="/path/to.parquet",
            profile_path="/path/to/profile.json"
        )

        assert result["status"] == "processing"
        mocked_post.assert_called_once()
        args, kwargs = mocked_post.call_args
        assert kwargs["json"]["dataset_name"] == "sales_data"
        assert kwargs["json"]["parquet_path"] == "/path/to.parquet"


@pytest.mark.asyncio
async def test_trigger_validation_retry_and_fail():
    """Test exponential backoff retries exhausted scenarios."""
    # Fast retries for testing
    service = ValidationTriggerService(base_url="http://fake-api", max_retries=2, initial_backoff=0.01)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mocked_post:
        with patch("app.services.validation_trigger.asyncio.sleep", new_callable=AsyncMock) as mocked_sleep:
            # Simulate network timeout
            mocked_post.side_effect = httpx.RequestError(
                "Mocked Connection Failure",
                request=MagicMock()
            )

            with pytest.raises(ValidationTriggerError) as exc_info:
                await service.trigger_validation(
                    dataset_name="sales_data",
                    batch_id="b_123",
                    parquet_path="/path",
                    profile_path="/path2"
                )

            assert "after 2 attempts" in str(exc_info.value)
            assert mocked_post.call_count == 2
            mocked_sleep.assert_awaited_once()


# ---------------------------------------------------------------------------
# HTTP 4xx error tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_validation_404_fails_immediately():
    """HTTP 404 is a non-recoverable client error; should fail on the first attempt only."""
    service = ValidationTriggerService(base_url="http://fake-api", max_retries=3, initial_backoff=0.01)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mocked_post:
        mocked_post.return_value = MagicMock(
            raise_for_status=MagicMock(side_effect=_make_http_status_error(404, "Not Found"))
        )

        with pytest.raises(ValidationTriggerError) as exc_info:
            await service.trigger_validation(
                dataset_name="sales_data",
                batch_id="b_404",
                parquet_path="/path",
                profile_path="/path2",
            )

        assert "Client error 404" in str(exc_info.value)
        # Must NOT retry on 4xx (except 429)
        assert mocked_post.call_count == 1


@pytest.mark.asyncio
async def test_trigger_validation_422_fails_immediately():
    """HTTP 422 Unprocessable Entity is a client error and should not be retried."""
    service = ValidationTriggerService(base_url="http://fake-api", max_retries=3, initial_backoff=0.01)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mocked_post:
        mocked_post.return_value = MagicMock(
            raise_for_status=MagicMock(side_effect=_make_http_status_error(422, "Unprocessable Entity"))
        )

        with pytest.raises(ValidationTriggerError) as exc_info:
            await service.trigger_validation(
                dataset_name="sales_data",
                batch_id="b_422",
                parquet_path="/path",
                profile_path="/path2",
            )

        assert "Client error 422" in str(exc_info.value)
        assert mocked_post.call_count == 1


@pytest.mark.asyncio
async def test_trigger_validation_429_is_retried():
    """HTTP 429 Too Many Requests should be retried (unlike other 4xx codes)."""
    service = ValidationTriggerService(base_url="http://fake-api", max_retries=2, initial_backoff=0.01)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mocked_post:
        with patch("app.services.validation_trigger.asyncio.sleep", new_callable=AsyncMock):
            success_response = MagicMock()
            success_response.raise_for_status.return_value = None
            success_response.json.return_value = {"status": "processing"}

            mocked_post.side_effect = [
                MagicMock(raise_for_status=MagicMock(side_effect=_make_http_status_error(429, "Rate Limited"))),
                success_response,
            ]

            result = await service.trigger_validation(
                dataset_name="sales_data",
                batch_id="b_429",
                parquet_path="/path",
                profile_path="/path2",
            )

        assert result["status"] == "processing"
        assert mocked_post.call_count == 2


# ---------------------------------------------------------------------------
# HTTP 5xx error tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_validation_500_retries_then_fails():
    """HTTP 500 Internal Server Error is transient; should retry exhausting all attempts."""
    service = ValidationTriggerService(base_url="http://fake-api", max_retries=3, initial_backoff=0.01)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mocked_post:
        with patch("app.services.validation_trigger.asyncio.sleep", new_callable=AsyncMock):
            mocked_post.return_value = MagicMock(
                raise_for_status=MagicMock(side_effect=_make_http_status_error(500, "Internal Server Error"))
            )

            with pytest.raises(ValidationTriggerError) as exc_info:
                await service.trigger_validation(
                    dataset_name="sales_data",
                    batch_id="b_500",
                    parquet_path="/path",
                    profile_path="/path2",
                )

        assert "after 3 attempts" in str(exc_info.value)
        assert mocked_post.call_count == 3


@pytest.mark.asyncio
async def test_trigger_validation_503_retries_then_succeeds():
    """HTTP 503 Service Unavailable is transient; should retry and succeed on the second call."""
    service = ValidationTriggerService(base_url="http://fake-api", max_retries=3, initial_backoff=0.01)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mocked_post:
        with patch("app.services.validation_trigger.asyncio.sleep", new_callable=AsyncMock):
            success_response = MagicMock()
            success_response.raise_for_status.return_value = None
            success_response.json.return_value = {"status": "accepted"}

            mocked_post.side_effect = [
                MagicMock(raise_for_status=MagicMock(side_effect=_make_http_status_error(503, "Service Unavailable"))),
                success_response,
            ]

            result = await service.trigger_validation(
                dataset_name="sales_data",
                batch_id="b_503",
                parquet_path="/path",
                profile_path="/path2",
            )

        assert result["status"] == "accepted"
        assert mocked_post.call_count == 2
