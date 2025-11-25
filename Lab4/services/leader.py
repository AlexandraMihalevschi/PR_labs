"""
Leader API for a semi-synchronous key-value store.

Only the leader accepts writes. Each write is replicated to every follower
concurrently, but the leader acknowledges success as soon as the configured
write quorum (number of follower confirmations) has been satisfied.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import time
from typing import Dict, List, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="KVStore Leader")

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------
FOLLOWERS: List[str] = [f.strip() for f in os.getenv("FOLLOWERS", "").split(",") if f.strip()]
WRITE_QUORUM = int(os.getenv("WRITE_QUORUM", "3"))
MIN_DELAY = float(os.getenv("MIN_DELAY", "0.01"))
MAX_DELAY = float(os.getenv("MAX_DELAY", "0.2"))
FOLLOWER_TIMEOUT = float(os.getenv("FOLLOWER_TIMEOUT", "2.5"))

if MIN_DELAY < 0 or MAX_DELAY < 0:
    raise ValueError("MIN_DELAY and MAX_DELAY must be non-negative.")

if MIN_DELAY > MAX_DELAY:
    raise ValueError("MIN_DELAY cannot be greater than MAX_DELAY.")

if FOLLOWERS and WRITE_QUORUM > len(FOLLOWERS):
    raise ValueError("WRITE_QUORUM cannot exceed number of configured followers.")

# --------------------------------------------------------------------------------------
# Shared in-memory state. Protected with an asyncio.Lock for concurrency safety.
# --------------------------------------------------------------------------------------
store: Dict[str, str] = {}
store_lock = asyncio.Lock()
store_version = 0
last_write_latency = 0.0
last_quorum_acks = 0


class KeyValuePayload(BaseModel):
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


class QuorumUpdateRequest(BaseModel):
    write_quorum: int = Field(gt=0)


def _sorted_store_items() -> List[Tuple[str, str]]:
    return sorted(store.items(), key=lambda kv: kv[0])


def _compute_checksum() -> str:
    """Return a SHA-256 checksum of the current store contents."""
    payload = json.dumps(_sorted_store_items(), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _commit_value(key: str, value: str) -> Dict[str, str]:
    """Write the value locally while holding the in-memory lock."""
    global store_version
    async with store_lock:
        store[key] = value
        store_version += 1
        return {
            "count": len(store),
            "version": store_version,
            "checksum": _compute_checksum(),
        }


async def replicate_to_follower(client: httpx.AsyncClient, follower_url: str, key: str, value: str) -> bool:
    """
    Replicate a write to a single follower with a randomized delay to simulate latency.
    """
    await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
    try:
        response = await client.post(
            f"{follower_url}/replicate",
            json={"key": key, "value": value},
        )
        return response.status_code == 200
    except Exception as exc:  # pragma: no cover - logged for observability
        print(f"[leader] Failed to replicate {key} -> {follower_url}: {exc}")
        return False


async def replicate_to_followers(key: str, value: str) -> int:
    """
    Replicate to all followers concurrently and return the number of acknowledgements.
    """
    if not FOLLOWERS:
        return 0

    async with httpx.AsyncClient(timeout=FOLLOWER_TIMEOUT) as client:
        tasks = [replicate_to_follower(client, follower, key, value) for follower in FOLLOWERS]
        results = await asyncio.gather(*tasks, return_exceptions=False)
    return sum(1 for result in results if result)


@app.get("/")
async def root():
    """Health check endpoint with quick diagnostics."""
    return {
        "status": "leader",
        "followers": len(FOLLOWERS),
        "write_quorum": WRITE_QUORUM,
        "version": store_version,
        "integrity_sign": "OK" if len(FOLLOWERS) >= WRITE_QUORUM else "CHECK",
    }


@app.get("/get/{key}")
async def get_value(key: str):
    """Return the stored value for a key."""
    async with store_lock:
        if key not in store:
            raise HTTPException(status_code=404, detail="Key not found")
        return {"key": key, "value": store[key]}


@app.post("/set")
async def set_value(payload: KeyValuePayload):
    """
    Accept writes on the leader, replicate them to every follower, and acknowledge
    once the configured write quorum is satisfied.
    """
    global last_write_latency, last_quorum_acks

    start_time = time.perf_counter()
    follower_acks = await replicate_to_followers(payload.key, payload.value)
    last_write_latency = time.perf_counter() - start_time
    last_quorum_acks = follower_acks

    if follower_acks < WRITE_QUORUM:
        raise HTTPException(
            status_code=503,
            detail=f"Write failed: only {follower_acks}/{WRITE_QUORUM} follower confirmations",
        )

    commit_metadata = await _commit_value(payload.key, payload.value)
    return {
        "status": "success",
        "key": payload.key,
        "value": payload.value,
        "replicated_to": follower_acks,
        "write_latency_s": last_write_latency,
        "store_version": commit_metadata["version"],
        "checksum": commit_metadata["checksum"],
    }


@app.get("/store")
async def get_store():
    """Return the entire store plus a checksum for quick validation."""
    async with store_lock:
        return {
            "store": dict(store),
            "count": len(store),
            "version": store_version,
            "checksum": _compute_checksum(),
        }


@app.get("/diagnostics")
async def diagnostics():
    """Expose a compact status block that integration tests can compare easily."""
    async with store_lock:
        checksum = _compute_checksum()
        return {
            "role": "leader",
            "keys": len(store),
            "version": store_version,
            "checksum": checksum,
            "last_write_latency_s": last_write_latency,
            "last_quorum_acks": last_quorum_acks,
            "integrity_sign": "OK" if last_quorum_acks >= WRITE_QUORUM else "WARN",
        }


@app.post("/config/write_quorum")
async def update_write_quorum(request: QuorumUpdateRequest):
    """
    Allow tests to adjust the quorum at runtime while keeping the environment variable
    as the default source of truth at startup.
    """
    global WRITE_QUORUM

    if FOLLOWERS and request.write_quorum > len(FOLLOWERS):
        raise HTTPException(
            status_code=400,
            detail="write_quorum cannot exceed total followers",
        )

    WRITE_QUORUM = request.write_quorum
    return {
        "status": "updated",
        "write_quorum": WRITE_QUORUM,
        "followers": len(FOLLOWERS),
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("services.leader:app", host="0.0.0.0", port=port, reload=False)
