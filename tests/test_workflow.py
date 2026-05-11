import respx
import httpx
import pytest
from src.services import HospitalService

BASE_URL = "https://mock-hospital-api.com"


@respx.mock
async def test_process_bulk_success():
    def mock_router(request):
        # Safety check: convert b"POST" to "POST" if your httpx version uses bytes
        method = request.method.decode("utf-8") if isinstance(request.method, bytes) else request.method

        if method == "POST":
            return httpx.Response(201, json={"id": 99})
        if method == "PATCH":
            return httpx.Response(200)
        return httpx.Response(404)

    respx.route(host="mock-hospital-api.com").mock(side_effect=mock_router)

    service = HospitalService(BASE_URL)
    csv_data = "name,address\nHosp A,123 St\nHosp B,456 St"
    result = await service.process_bulk_csv(csv_data)

    assert result["failed_hospitals"] == 0, f"Failures: {result['hospitals']}"
    assert result["processed_hospitals"] == 2
    assert result["batch_activated"] is True


@respx.mock
async def test_process_bulk_partial_failure_triggers_rollback():
    post_count = 0
    rollback_called = False

    def mock_router(request):
        nonlocal post_count, rollback_called
        method = request.method.decode("utf-8") if isinstance(request.method, bytes) else request.method

        if method == "POST":
            post_count += 1
            if post_count == 2:
                return httpx.Response(500, text="Internal Server Error")
            return httpx.Response(201, json={"id": 100})

        if method == "DELETE":
            rollback_called = True
            return httpx.Response(204)

        return httpx.Response(404)

    respx.route(host="mock-hospital-api.com").mock(side_effect=mock_router)

    service = HospitalService(BASE_URL)
    csv_data = "name,address\nHosp A,123 St\nHosp B,456 St"
    result = await service.process_bulk_csv(csv_data)

    assert result["processed_hospitals"] == 1
    assert result["failed_hospitals"] == 1
    assert result["batch_activated"] is False
    assert rollback_called is True, "The rollback DELETE method was never called!"


@respx.mock
async def test_process_bulk_idempotent_retry():
    def mock_router(request):
        method = request.method.decode("utf-8") if isinstance(request.method, bytes) else request.method

        if method == "POST":
            return httpx.Response(200, json={"id": 101})  # Already exists
        if method == "PATCH":
            return httpx.Response(400, text="batch is already active")
        return httpx.Response(404)

    respx.route(host="mock-hospital-api.com").mock(side_effect=mock_router)

    service = HospitalService(BASE_URL)
    csv_data = "name,address\nHosp A,123 St"

    result = await service.process_bulk_csv(csv_data, batch_id="existing-uuid-123")

    assert result["failed_hospitals"] == 0, f"Failures: {result['hospitals']}"
    assert result["processed_hospitals"] == 1
    assert result["batch_activated"] is False
    assert result["hospitals"][0]["status"] in ("created", "already_active")
