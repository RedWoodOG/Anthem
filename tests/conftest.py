"""
Pytest configuration for Anthem tests.

Integration tests (marked with @pytest.mark.integration) are auto-skipped
when required services aren't running. The service check runs once per session.
Unit tests run regardless.
"""

import pytest
import asyncio
import httpx


SERVICE_PORTS = {
    "gateway": "http://localhost:9200",
    "broker": "http://localhost:8100",
    "bue": "http://localhost:9000",
    "urpe": "http://localhost:7300",
    "uie": "http://localhost:8000",
}

_services_checked = False
_services_unreachable = None


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test (requires running services)"
    )


def _check_services_once():
    """Check all services once, cache the result."""
    global _services_checked, _services_unreachable
    if _services_checked:
        return _services_unreachable

    async def _check():
        async with httpx.AsyncClient(timeout=2.0) as client:
            unreachable = []
            for name, url in SERVICE_PORTS.items():
                try:
                    r = await client.get(f"{url}/health")
                    if r.status_code != 200:
                        unreachable.append(name)
                except Exception:
                    unreachable.append(name)
            return unreachable

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        _services_unreachable = loop.run_until_complete(_check())
    finally:
        loop.close()

    _services_checked = True
    return _services_unreachable


@pytest.fixture(autouse=True)
def skip_integration_if_services_down(request):
    """Skip integration tests when services aren't running. Checked once."""
    if "integration" not in request.node.keywords:
        return

    unreachable = _check_services_once()
    if unreachable:
        pytest.skip(f"Services not running: {', '.join(unreachable)}")


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client
