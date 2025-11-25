"""
Integration tests for the leader/follower replication setup.
"""
from __future__ import annotations

import asyncio
from typing import Dict

import httpx
import pytest
import pytest_asyncio

LEADER_URL = "http://localhost:8000"
FOLLOWER_URLS = [
    "http://localhost:8001",
    "http://localhost:8002",
    "http://localhost:8003",
    "http://localhost:8004",
    "http://localhost:8005",
]

pytestmark = pytest.mark.asyncio


async def wait_for_services(max_retries: int = 60, delay: float = 0.5) -> None:
    """Wait for all services to be ready, with better error reporting."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        for attempt in range(max_retries):
            try:
                # Check leader
                try:
                    leader_resp = await client.get(LEADER_URL)
                    leader_ready = leader_resp.status_code == 200
                except Exception:
                    leader_ready = False
                
                # Check followers
                follower_statuses = await asyncio.gather(
                    *[client.get(url) for url in FOLLOWER_URLS],
                    return_exceptions=True,
                )
                
                ready_count = sum(
                    1 for resp in follower_statuses
                    if isinstance(resp, httpx.Response) and resp.status_code == 200
                )
                
                if leader_ready and ready_count == len(FOLLOWER_URLS):
                    return
                    
            except Exception:
                pass
            
            await asyncio.sleep(delay)
    
    raise RuntimeError(f"Services did not become ready after {max_retries * delay} seconds. Check docker compose logs.")


@pytest_asyncio.fixture(scope="function")
async def http_client():
    async with httpx.AsyncClient(timeout=15.0) as client:
        yield client


@pytest_asyncio.fixture(scope="function", autouse=True)
async def ensure_cluster_ready():
    await wait_for_services()
    yield


async def fetch_store(client: httpx.AsyncClient, base_url: str) -> Dict[str, Dict[str, str]]:
    response = await client.get(f"{base_url}/store")
    response.raise_for_status()
    return response.json()


async def fetch_diagnostics(client: httpx.AsyncClient, base_url: str) -> Dict[str, str]:
    response = await client.get(f"{base_url}/diagnostics")
    response.raise_for_status()
    return response.json()


async def write_key(client: httpx.AsyncClient, key: str, value: str) -> httpx.Response:
    response = await client.post(f"{LEADER_URL}/set", json={"key": key, "value": value})
    return response


async def set_write_quorum(client: httpx.AsyncClient, quorum: int) -> httpx.Response:
    response = await client.post(f"{LEADER_URL}/config/write_quorum", json={"write_quorum": quorum})
    response.raise_for_status()
    return response


async def test_basic_write_read(http_client: httpx.AsyncClient):
    test_id = "basic_write_read"
    response = await write_key(http_client, f"{test_id}_test_key", "test_value")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["replicated_to"] >= 1

    leader_value = await http_client.get(f"{LEADER_URL}/get/{test_id}_test_key")
    assert leader_value.status_code == 200
    assert leader_value.json()["value"] == "test_value"

    for follower_url in FOLLOWER_URLS:
        follower_value = await http_client.get(f"{follower_url}/get/{test_id}_test_key")
        assert follower_value.status_code == 200
        assert follower_value.json()["value"] == "test_value"


async def test_multiple_writes_consistency(http_client: httpx.AsyncClient):
    test_id = "multi_write"
    fixtures = {f"{test_id}_key{i}": f"value{i}" for i in range(3)}
    for key, value in fixtures.items():
        response = await write_key(http_client, key, value)
        assert response.status_code == 200

    # Wait for all background replications to complete
    await asyncio.sleep(1.0)

    for key, expected in fixtures.items():
        leader_resp = await http_client.get(f"{LEADER_URL}/get/{key}")
        assert leader_resp.status_code == 200
        assert leader_resp.json()["value"] == expected

    for follower_url in FOLLOWER_URLS:
        for key, expected in fixtures.items():
            follower_resp = await http_client.get(f"{follower_url}/get/{key}")
            assert follower_resp.status_code == 200, f"Key {key} not found on {follower_url}"
            assert follower_resp.json()["value"] == expected


async def test_concurrent_writes(http_client: httpx.AsyncClient):
    async def write_pair(idx: int):
        resp = await write_key(http_client, f"concurrent_{idx}", f"value_{idx}")
        assert resp.status_code == 200

    await asyncio.gather(*[write_pair(i) for i in range(20)])
    # Wait for all background replications to complete (20 concurrent writes)
    await asyncio.sleep(2.0)

    for i in range(20):
        key = f"concurrent_{i}"
        leader_resp = await http_client.get(f"{LEADER_URL}/get/{key}")
        assert leader_resp.status_code == 200
        assert leader_resp.json()["value"] == f"value_{i}"

        follower_resp = await http_client.get(f"{FOLLOWER_URLS[0]}/get/{key}")
        assert follower_resp.status_code == 200
        assert follower_resp.json()["value"] == f"value_{i}"


async def test_diagnostics_checksums_match(http_client: httpx.AsyncClient):
    for i in range(5):
        await write_key(http_client, f"diag_key_{i}", f"diag_value_{i}")

    # Wait for all background replications to complete (MAX_DELAY=0.1s, allow extra buffer)
    await asyncio.sleep(1.0)

    leader_diag = await fetch_diagnostics(http_client, LEADER_URL)
    for follower in FOLLOWER_URLS:
        follower_diag = await fetch_diagnostics(http_client, follower)
        assert follower_diag["checksum"] == leader_diag["checksum"], \
            f"Checksum mismatch with {follower}: leader={leader_diag['checksum']}, follower={follower_diag['checksum']}"
        assert follower_diag["integrity_sign"] in {"OK", "EMPTY"}


async def test_runtime_write_quorum_update(http_client: httpx.AsyncClient):
    update_resp = await set_write_quorum(http_client, 2)
    assert update_resp.json()["write_quorum"] == 2

    write_resp = await write_key(http_client, "quorum_key", "quorum_value")
    assert write_resp.status_code == 200
    assert write_resp.json()["replicated_to"] >= 2

    # Reset quorum back to the default so other tests are not affected.
    await set_write_quorum(http_client, 3)


async def test_stores_match_after_writes(http_client: httpx.AsyncClient):
    for i in range(10):
        await write_key(http_client, f"consistency_key_{i}", f"value_{i}")

    # Wait for all background replications to complete (MAX_DELAY=0.1s, allow extra buffer)
    await asyncio.sleep(1.5)

    leader_store = await fetch_store(http_client, LEADER_URL)
    for follower in FOLLOWER_URLS:
        follower_store = await fetch_store(http_client, follower)
        assert follower_store["checksum"] == leader_store["checksum"], \
            f"Checksum mismatch with {follower}: leader={leader_store['checksum']}, follower={follower_store['checksum']}"
        assert follower_store["count"] == leader_store["count"], \
            f"Count mismatch with {follower}: leader has {leader_store['count']}, follower has {follower_store['count']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
