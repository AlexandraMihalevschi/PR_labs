# Lab 4: Leaders and followers

**Student Name:** Mihalevschi Alexandra
**Date:** 25.11.2025
**Course:** Network Programming

## Summary

Implement a concurrent single-leader key-value store with semi-synchronous replication to 5 followers (each in its own Docker container), configurable write quorum and leader-side variable network lag; provide web JSON API, integration tests, and a performance study of write-quorum vs average write latency.

---

---

## 1. Design Overview

### 1.1 System model

- Single **leader** accepts client **writes** (PUT/POST) and **reads** (GET).
- **Leader** replicates writes to **5 followers** (semi-synchronous replication).
- **Followers** accept replication requests and apply updates to their local store.
- **Only leader** accepts writes from clients; followers only accept replication from leader (and may accept reads if desired).
- All servers execute requests concurrently (asyncio + thread-safe store).

### 1.2 Semi-synchronous replication

- Leader sends replicate requests to all followers concurrently.
- Leader waits for **N confirmations** (configurable: `WRITE_QUORUM`) before reporting success to client.

  - `WRITE_QUORUM` is set via environment variable in docker-compose (e.g. 1..5).

- If confirmations do not reach `WRITE_QUORUM` within a configurable timeout, the leader responds with an error/timeout.
- This provides a tunable trade-off between latency and durability.

### 1.3 Leader-side network-lag simulation

- Before sending each replicate request, the leader sleeps a random delay in `[MIN_DELAY, MAX_DELAY]` (ms).
- `MIN_DELAY` and `MAX_DELAY` are supplied via environment variables to the leader container.
- Replication requests are dispatched concurrently, so each follower sees different delays.

### 1.4 Concurrency

- HTTP server implemented with `aiohttp` (async) or `FastAPI` + `uvicorn` (async) — recommended: `aiohttp` for simplicity.
- Store implemented with fine-grained locks or `asyncio.Lock()` per key to allow concurrent writes to different keys.
- Leader dispatches replication tasks using `asyncio.gather()` so followers are contacted concurrently.

---

## 2. API (JSON over HTTP)

### Leader endpoints

- `POST /set`
  Body: `{ "key": "k", "value": "v" }`
  Response: `200 OK` `{ "status": "success", "key": "k", "value": "v", "replicated_to": 3, "write_latency_s": 0.123, "store_version": 42, "checksum": "..." }` on success.

- `GET /get/{key}`
  Response: `200 OK` `{ "key": "k", "value": "v" }`

- `GET /store`
  Response: `200 OK` `{ "store": {...}, "count": 10, "version": 42, "checksum": "..." }`

- `GET /diagnostics`
  Response: `200 OK` `{ "role": "leader", "keys": 10, "version": 42, "checksum": "...", "integrity_sign": "OK" }`

- `POST /config/write_quorum`
  Body: `{ "write_quorum": 3 }`
  Response: `200 OK` `{ "status": "updated", "write_quorum": 3, "followers": 5 }`

- `GET /` (health check)

### Follower endpoints

- `POST /replicate` (apply replication from leader)
  Body: `{ "key": "k", "value": "v" }`
  Response: `200 OK` `{ "status": "replicated", "key": "k", "value": "v", "version": 42, "checksum": "..." }`

- `GET /get/{key}` (read from follower)
  Response: `200 OK` `{ "key": "k", "value": "v" }`

- `GET /store` (return entire replica store)

- `GET /diagnostics` (status and integrity signals)

- `GET /` (health check)

---

## 3. Configuration via environment variables (docker-compose)

Put in `docker-compose.yml` environment settings for each service. Key env vars:

- `FOLLOWERS=http://follower1:8001,http://follower2:8002,...` (comma-separated URLs)
- `WRITE_QUORUM=3` # leader waits for 3 follower confirmations (configurable 1-5)
- `FOLLOWER_TIMEOUT=2.5` # how long leader waits for follower responses (in seconds)
- `MIN_DELAY=0.05` # min simulated delay per replicate (in seconds)
- `MAX_DELAY=0.5` # max simulated delay per replicate (in seconds)
- `PORT=8000` # port for the service
- `FOLLOWER_ID=follower1` # identifier for followers (for logging/diagnostics)

Example `docker-compose.yml` snippet:

```yaml
version: "3.8"
services:
  leader:
    build: .
    command: python services/leader.py
    environment:
      - PORT=8000
      - FOLLOWERS=http://follower1:8001,http://follower2:8002,http://follower3:8003,http://follower4:8004,http://follower5:8005
      - WRITE_QUORUM=3
      - MIN_DELAY=0.05
      - MAX_DELAY=0.5
      - FOLLOWER_TIMEOUT=2.5
    ports:
      - "8000:8000"
    depends_on:
      - follower1
      - follower2
      - follower3
      - follower4
      - follower5
  follower1:
    build: .
    command: python services/follower.py
    environment:
      - PORT=8001
      - FOLLOWER_ID=follower1
    ports:
      - "8001:8001"
  follower2:
    build: .
    command: python services/follower.py
    environment:
      - PORT=8002
      - FOLLOWER_ID=follower2
    ports:
      - "8002:8002"
  # follower3, follower4, follower5 configured similarly on ports 8003-8005
```

---

## 4. Implementation

### 4.1 In-memory concurrent KV store

- Uses a `dict` mapping `key -> value`.
- Protected with a single `asyncio.Lock()` for simplicity.
- Global `store_version` counter incremented on each write.
- `async def _commit_value(key, value)` acquires lock, writes value, increments version, computes checksum.
- Checksum computed as SHA-256 of sorted key-value pairs for consistency verification.

### 4.2 leader.py

- Implements FastAPI server with uvicorn.
- On `POST /set` (write request):

  1. Increment local `version` counter.
  2. Apply locally: `await _commit_value(key, value)` (atomic with lock).
  3. Concurrently replicate to all followers.
  4. For each follower, create an asyncio task that:
     - Sleeps a random delay in `[MIN_DELAY, MAX_DELAY]`
     - POSTs to `{follower_url}/replicate` with `{key, value}`
     - Returns success/failure
  5. Use `asyncio.wait(pending_tasks, return_when=FIRST_COMPLETED)` to return as soon as `WRITE_QUORUM` confirmations arrive.
  6. Respond to client with success only if quorum reached; otherwise return 503 error.

- Additional endpoints:
  - `POST /config/write_quorum` - adjust quorum at runtime
  - `GET /store` - return full store + checksum
  - `GET /diagnostics` - expose status signals

### 4.3 follower.py

- Implements FastAPI server with uvicorn on its configured PORT.
- Exposes `POST /replicate` endpoint. On receiving a replication request:

  1. Extract key and value from request JSON.
  2. Acquire global lock and write value/version atomically.
  3. Increment local version counter and compute checksum.
  4. Return success with metadata (version, checksum).

- Followers run independently and accept concurrent replication requests from leader.
- Additional endpoints:
  - `GET /get/{key}` - read a value
  - `GET /store` - return full store + checksum
  - `GET /diagnostics` - expose status signals

![Result](results/img.png)
![Result](result.png)

Results during another runs:
![Result](result_iterations/1.png)
![Result](result_iterations/2.png)
![Result](result_iterations/3.png)
![Result](result_iterations/4.png)
![Result](result_iterations/5.png)



---

## 5. Integration Tests

**Goal:** Verify leader + 5 followers work together with semi-synchronous replication and configurable write quorum.

**Test suite (`tests/test_integration.py`) includes:**

1. `test_basic_write_read` - Write a key and verify it's present on leader and all followers.
2. `test_multiple_writes_consistency` - Multiple writes with consistency verification.
3. `test_concurrent_writes` - 20 concurrent writes to test concurrency model.
4. `test_diagnostics_checksums_match` - Verify all replicas have matching checksums.
5. `test_runtime_write_quorum_update` - Test dynamic quorum adjustment via API.
6. `test_stores_match_after_writes` - Final consistency verification across all nodes.

**Key features:**

- Uses `httpx.AsyncClient` for async HTTP requests
- Auto-waits for all services to be ready (60 retries, 0.5s delay)
- Includes error handling and timeout management
- Robust to transient delays with retries

**Run integration tests:**

```bash
pytest tests/test_integration.py -v
```

**Expected behavior:**

- All tests pass when services are running
- Services must be started first: `docker-compose up -d`
- Tests verify writes reach the configured `WRITE_QUORUM`
- All follower stores converge to match leader store

![Result](results/image.png)

---

## 6. Performance Experiment

### 6.1 Goal

Measure how write latency varies with `WRITE_QUORUM` (1-5). Quantify the trade-off between durability and latency. Detect any race conditions or data consistency issues.

### 6.2 Method

**`scripts/performance_analysis.py`** - Comprehensive benchmark:

- For each quorum value (1-5):
  - Set quorum via runtime API: `POST /config/write_quorum`
  - Perform 100 writes total, 10 concurrent at a time (semaphore)
  - Spread across 10 keys
  - Measure: avg, median, p95, p99 latencies
  - Check for race conditions and consistency
  - Save results to `results/performance_results.json`

**`tests/test_single_quorum.py`** - Single quorum tester:

- Usage: `python tests/test_single_quorum.py <quorum_value>`
- Tests one specific quorum value
- Saves per-quorum results to `results/results_quorum_<N>.json`
- Checks for race conditions and consistency issues

**`scripts/plot_results.py`** - Plot generator:

- Reads `results/results_quorum_*.json` files
- Generates `results/write_quorum_vs_latency.png`
- Shows average, median, p95, p99 latencies

### 6.3 Metrics collected

```json
{
  "quorum": 3,
  "avg_latency_ms": 145.2,
  "median_latency_ms": 138.5,
  "p95_latency_ms": 212.3,
  "p99_latency_ms": 245.8,
  "success_rate": 0.98,
  "total_time": 15.2,
  "num_successful": 98,
  "consistency": {...},
  "race_condition_check": {...}
}
```

### 6.4 Expected results and explanation

- **Write quorum = 1**: Leader returns after 1st follower ACK. **Lowest latency** (~50-100ms), minimal durability.
- **Write quorum = 2-3**: Moderate latency (~100-200ms), good durability balance.
- **Write quorum = 4-5**: Higher latency (~150-250ms), maximum durability (all replicas guaranteed).

**Why latency increases with quorum:**

- With independent random delays per follower in `[MIN_DELAY, MAX_DELAY]`, waiting for the k-th fastest response takes longer as k increases.
- Example: with MIN_DELAY=50ms, MAX_DELAY=500ms:
  - Quorum=1: wait for 1st (fastest) → ~50-100ms
  - Quorum=3: wait for 3rd (median) → ~200-250ms
  - Quorum=5: wait for 5th (slowest) → ~400-500ms

**Concurrency effect:**

- 10 concurrent writes stress the system; followers queue requests
- Queuing delays add on top of network delays, amplifying latency
- Effect is more pronounced at higher quorums

**Plot characteristics:**

- Monotonically increasing curve (latency vs quorum)
- May show non-linear growth due to queuing effects
- Variance increases with quorum (wider range of latencies at higher quorums)

---

## 7. Data Consistency Check After Writes

### 7.1 What to check

- After all writes completed, verify that every follower's stored `(key -> (value, version))` equals the leader's final store for all keys.

### 7.2 Possible outcomes and explanations

1. **All replicas match leader:** If leader waited for `WRITE_QUORUM` successes but the replication tasks still completed for remaining followers (even if after the leader responded), final convergence can still occur. With eventual delivery and no failures, replicas converge.
2. **Some replicas lag behind:** If leader returns success after quorum but some followers were slow or unreachable and did not apply the update, they'll be missing that write until retry/repair. This is expected behavior with semi-sync replication and smaller quorum.
3. **Conflict/ordering issues:** If leader restarts or network partitions occur, versions or ordering must be used to ensure last-write-wins (or stronger consistency if implemented). Using monotonic `version` avoids reordering.

---

## 8. Commands and How to Run

### 8.1 Prerequisites

```bash
# Install Python dependencies
pip install -r requirements.txt

# Ensure Docker and Docker Compose are installed
docker --version
docker-compose --version
```

### 8.2 Build and start services

```bash
# Build images
docker-compose build

# Start leader + 5 followers in background
docker-compose up -d

# Wait for services to be ready (monitor logs)
docker-compose logs -f
```

### 8.3 Run integration tests

```bash
# Run all integration tests
pytest tests/test_integration.py -v

# Run specific test
pytest tests/test_integration.py::test_basic_write_read -v
```

### 8.4 Run performance benchmarks

```bash
# Option 1: Full benchmark (all quorums 1-5)
python scripts/performance_analysis.py

# Option 2: Single quorum test
python tests/test_single_quorum.py 3  # Test with WRITE_QUORUM=3

# Generate plot from results
python scripts/plot_results.py
```

### 8.5 View results

```bash
# Results are saved to results/ directory
ls -la results/

# View JSON results
cat results/performance_results.json

# View generated plot
open results/write_quorum_vs_latency.png  # macOS
xdg-open results/write_quorum_vs_latency.png  # Linux
start results/write_quorum_vs_latency.png  # Windows
```

### 8.6 Clean up

```bash
# Stop and remove containers
docker-compose down

# Also remove volumes (if needed)
docker-compose down -v

# View logs before cleanup
docker-compose logs
```

### Environment Variable Defaults

| Variable           | Default   | Range       | Notes                     |
| ------------------ | --------- | ----------- | ------------------------- | --- |
| `WRITE_QUORUM`     | 3         | 1-5         | Can be changed at runtime |
| `MIN_DELAY`        | 0.05      | >= 0        | Seconds                   |
| `MAX_DELAY`        | 0.5       | > MIN_DELAY | Seconds                   |
| `FOLLOWER_TIMEOUT` | 2.5       | > 0         | Seconds; total wait time  |
| `PORT` (leader)    | 8000      | 1024-65535  | HTTP server port          |
| `PORT` (followers) | 8001-8005 | 1024-65535  | One per follower          | `   |

---
