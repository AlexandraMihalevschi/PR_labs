"""
Integration tests for the leader/follower replication setup.
"""
from __future__ import annotations

import asyncio
from typing import Dict

import httpx
import pytest

LEADER_URL = "http://localhost:8000"
FOLLOWER_URLS = [
    "http://localhost:8001",
    "http://localhost:8002",
    "http://localhost:8003",
    "http://localhost:8004",
    "http://localhost:8005",
]

pytestmark = pytest.mark.asyncio


async def wait_for_services(max_retries: int = 30, delay: float = 0.5) -> None:
    async with httpx.AsyncClient(timeout=2.0) as client:
        for _ in range(max_retries):
            try:
                leader_ready = (await client.get(LEADER_URL)).status_code == 200
                follower_statuses = await asyncio.gather(
                    *[client.get(url) for url in FOLLOWER_URLS],
                    return_exceptions=True,
                )
                followers_ready = all(
                    isinstance(resp, httpx.Response) and resp.status_code == 200
                    for resp in follower_statuses
                )
                if leader_ready and followers_ready:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(delay)
    raise RuntimeError("Services did not become ready in time")


@pytest.fixture(scope="session")
async def http_client():
    async with httpx.AsyncClient(timeout=15.0) as client:
        yield client


@pytest.fixture(scope="module", autouse=True)
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


async def test_basic_write_read(http_client: httpx.AsyncClient):
    response = await write_key(http_client, "test_key", "test_value")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["replicated_to"] >= 1

    leader_value = await http_client.get(f"{LEADER_URL}/get/test_key")
    assert leader_value.status_code == 200
    assert leader_value.json()["value"] == "test_value"

    for follower_url in FOLLOWER_URLS:
        follower_value = await http_client.get(f"{follower_url}/get/test_key")
        assert follower_value.status_code == 200
        assert follower_value.json()["value"] == "test_value"


async def test_multiple_writes_consistency(http_client: httpx.AsyncClient):
    fixtures = {f"key{i}": f"value{i}" for i in range(3)}
    for key, value in fixtures.items():
        response = await write_key(http_client, key, value)
        assert response.status_code == 200

    await asyncio.sleep(0.2)

    for key, expected in fixtures.items():
        leader_resp = await http_client.get(f"{LEADER_URL}/get/{key}")
        assert leader_resp.status_code == 200
        assert leader_resp.json()["value"] == expected

    for follower_url in FOLLOWER_URLS:
        for key, expected in fixtures.items():
            follower_resp = await http_client.get(f"{follower_url}/get/{key}")
            assert follower_resp.status_code == 200
            assert follower_resp.json()["value"] == expected


async def test_concurrent_writes(http_client: httpx.AsyncClient):
    async def write_pair(idx: int):
        resp = await write_key(http_client, f"concurrent_{idx}", f"value_{idx}")
        assert resp.status_code == 200

    await asyncio.gather(*[write_pair(i) for i in range(20)])
    await asyncio.sleep(0.5)

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

    await asyncio.sleep(0.5)

    leader_diag = await fetch_diagnostics(http_client, LEADER_URL)
    for follower in FOLLOWER_URLS:
        follower_diag = await fetch_diagnostics(http_client, follower)
        assert follower_diag["checksum"] == leader_diag["checksum"]
        assert follower_diag["integrity_sign"] in {"OK", "EMPTY"}


async def test_runtime_write_quorum_update(http_client: httpx.AsyncClient):
    update_resp = await http_client.post(
        f"{LEADER_URL}/config/write_quorum", json={"write_quorum": 2}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["write_quorum"] == 2

    write_resp = await write_key(http_client, "quorum_key", "quorum_value")
    assert write_resp.status_code == 200
    assert write_resp.json()["replicated_to"] >= 2


async def test_stores_match_after_writes(http_client: httpx.AsyncClient):
    for i in range(10):
        await write_key(http_client, f"consistency_key_{i}", f"value_{i}")

    await asyncio.sleep(0.5)

    leader_store = await fetch_store(http_client, LEADER_URL)
    for follower in FOLLOWER_URLS:
        follower_store = await fetch_store(http_client, follower)
        assert follower_store["checksum"] == leader_store["checksum"]
        assert follower_store["count"] == leader_store["count"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
