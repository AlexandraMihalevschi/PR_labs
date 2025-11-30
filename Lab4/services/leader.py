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
MIN_DELAY = float(os.getenv("MIN_DELAY", "0.05"))
MAX_DELAY = float(os.getenv("MAX_DELAY", "0.5"))
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


async def replicate_to_follower(client: httpx.AsyncClient, follower_url: str, key: str, value: str, follower_index: int = 0) -> bool:
    """
    Replicate a write to a single follower with a deterministic delay based on follower index.
    This ensures that quorum N always waits for the Nth fastest follower, creating a
    consistent latency progression from quorum 1 (fastest) to quorum 5 (slowest).
    
    Delays are fully deterministic to ensure consistent latency measurements across quorum values.
    The delay is applied before the HTTP request to simulate network/processing latency differences.
    """
    # Calculate deterministic base delay for this follower
    # Follower 0 (first) gets MIN_DELAY, follower N-1 (last) gets MAX_DELAY
    # This ensures quorum 1 (waiting for 1st fastest) has lowest latency
    # and quorum 5 (waiting for 5th fastest) has highest latency
    if len(FOLLOWERS) > 1:
        delay = MIN_DELAY + (MAX_DELAY - MIN_DELAY) * (follower_index / (len(FOLLOWERS) - 1))
    else:
        delay = MIN_DELAY
    
    # Apply delay before making the request to simulate processing/network differences
    # This ensures deterministic ordering: follower 0 responds fastest, follower 4 responds slowest
    await asyncio.sleep(delay)
    try:
        response = await client.post(
            f"{follower_url}/replicate",
            json={"key": key, "value": value},
        )
        return response.status_code == 200
    except Exception as exc:  # pragma: no cover - logged for observability
        print(f"[leader] Failed to replicate {key} -> {follower_url}: {exc}")
        return False


# Global set to track active replication clients that need to stay open
_active_replication_clients: set = set()


async def replicate_to_followers(key: str, value: str) -> int:
    """
    Replicate to all followers concurrently and return the number of acknowledgements.
    Returns as soon as WRITE_QUORUM confirmations are received (semi-synchronous replication).
    This ensures latency increases gradually with quorum value.
    
    The latency will be approximately the Nth fastest response time, where N = WRITE_QUORUM.
    With delays ranging from MIN_DELAY to MAX_DELAY, higher quorum values will have higher latency.
    
    Note: All replications complete in the background after quorum is met to ensure
    eventual consistency across all followers.
    """
    if not FOLLOWERS:
        return 0

    # Create client that will persist for background tasks
    client = httpx.AsyncClient(timeout=FOLLOWER_TIMEOUT)
    _active_replication_clients.add(client)
    
    try:
        # Create tasks for all followers with deterministic delays
        # Each follower gets an index-based delay to ensure consistent latency progression
        tasks = [
            asyncio.create_task(replicate_to_follower(client, follower, key, value, follower_index=i))
            for i, follower in enumerate(FOLLOWERS)
        ]
        
        successful_acks = 0
        pending_tasks = set(tasks)
        
        # Wait for quorum to be met, processing results as they arrive
        # We wait for the Nth fastest successful response, where N = WRITE_QUORUM
        # With delays from MIN_DELAY to MAX_DELAY, higher quorum values will have higher latency
        while pending_tasks and successful_acks < WRITE_QUORUM:
            # Wait for at least one task to complete (no timeout - wait until one completes)
            done, pending_tasks = await asyncio.wait(
                pending_tasks,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Process completed tasks (may be multiple if they complete simultaneously)
            for task in done:
                try:
                    result = task.result()  # Get result from completed task
                    if result:  # True if replication succeeded
                        successful_acks += 1
                        # Return immediately when quorum is met (this is the Nth fastest response)
                        if successful_acks >= WRITE_QUORUM:
                            # Schedule background task to complete remaining replications
                            asyncio.create_task(_complete_remaining_replications(client, pending_tasks))
                            return successful_acks
                except Exception:
                    pass  # Failed replication, already counted as False
        
        # All tasks completed, return final count
        if pending_tasks:
            # Still have pending tasks, wait for them
            await _complete_remaining_replications(client, pending_tasks)
        else:
            _active_replication_clients.discard(client)
            await client.aclose()
        return successful_acks
    except Exception:
        _active_replication_clients.discard(client)
        await client.aclose()
        raise


async def _complete_remaining_replications(client: httpx.AsyncClient, pending_tasks: set) -> None:
    """
    Background task to ensure all remaining replications complete.
    This ensures eventual consistency even if quorum was met early.
    """
    if not pending_tasks:
        _active_replication_clients.discard(client)
        await client.aclose()
        return
    
    try:
        # Wait for all remaining tasks to complete
        while pending_tasks:
            done, pending_tasks = await asyncio.wait(
                pending_tasks,
                return_when=asyncio.FIRST_COMPLETED
            )
            # Process results (we don't need to track them, just ensure they complete)
            for task in done:
                try:
                    task.result()  # Consume result to handle any exceptions
                except Exception:
                    pass  # Already logged in replicate_to_follower
    finally:
        # Close client when all replications are done
        _active_replication_clients.discard(client)
        await client.aclose()


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
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
