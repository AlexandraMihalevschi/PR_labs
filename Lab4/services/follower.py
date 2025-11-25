"""
Follower service that receives replication requests from the leader.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from typing import Dict, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="KVStore Follower")

FOLLOWER_ID = os.getenv("FOLLOWER_ID", "unknown")
PORT = int(os.getenv("PORT", "8000"))

store: Dict[str, str] = {}
store_lock = asyncio.Lock()
store_version = 0


class ReplicationPayload(BaseModel):
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


def _sorted_store_items() -> Tuple[Tuple[str, str], ...]:
    return tuple(sorted(store.items(), key=lambda kv: kv[0]))


def _checksum() -> str:
    payload = json.dumps(_sorted_store_items(), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@app.get("/")
async def root():
    """Simple health endpoint with integrity hints."""
    async with store_lock:
        return {
            "status": "follower",
            "id": FOLLOWER_ID,
            "keys": len(store),
            "version": store_version,
            "integrity_sign": "OK" if store else "EMPTY",
        }


@app.post("/replicate")
async def replicate(payload: ReplicationPayload):
    """Apply a replicated write from the leader."""
    global store_version
    async with store_lock:
        store[payload.key] = payload.value
        store_version += 1
        checksum = _checksum()
    return {
        "status": "replicated",
        "key": payload.key,
        "value": payload.value,
        "version": store_version,
        "checksum": checksum,
    }


@app.get("/get/{key}")
async def get_value(key: str):
    """Read a value from the replica store."""
    async with store_lock:
        if key not in store:
            raise HTTPException(status_code=404, detail="Key not found")
        return {"key": key, "value": store[key]}


@app.get("/store")
async def get_store():
    """Return the entire replica store plus a checksum for verification."""
    async with store_lock:
        return {
            "store": dict(store),
            "count": len(store),
            "follower_id": FOLLOWER_ID,
            "version": store_version,
            "checksum": _checksum(),
        }


@app.get("/diagnostics")
async def diagnostics():
    """Expose extra signals so the integration test can assert data parity."""
    async with store_lock:
        return {
            "role": "follower",
            "id": FOLLOWER_ID,
            "keys": len(store),
            "version": store_version,
            "checksum": _checksum(),
            "integrity_sign": "OK" if store else "EMPTY",
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)
