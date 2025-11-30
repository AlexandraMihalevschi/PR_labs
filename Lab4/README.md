# Lab 4: Leaders and followers

**Student Name:** Mihalevschi Alexandra
**Date:** 25.11.2025
**Course:** Network Programming

## Summary

Implement a concurrent single-leader key-value store with semi-synchronous replication to 5 followers (each in its own Docker container), configurable write quorum and leader-side variable network lag; provide web JSON API, integration tests, and a performance study of write-quorum vs average write latency.

---

## 1. System details

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
- **Checksum computation**: SHA-256 hash of sorted key-value pairs (JSON-serialized) for data consistency verification.
  - Ensures deterministic checksum regardless of insertion order
  - Used to detect data inconsistencies between leader and followers

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
  - `GET /store` - return full store + checksum for consistency verification
  - `GET /diagnostics` - expose status signals including checksum for data integrity checks

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
  - `GET /store` - return full store + checksum for consistency verification
  - `GET /diagnostics` - expose status signals including checksum for data integrity checks

---

## 5. Integration Tests

**Goal:** Verify leader + 5 followers work together with semi-synchronous replication and configurable write quorum.

**Test suite (`tests/test_integration.py`) includes:**

1. `test_basic_write_read` - Write a key and verify it's present on leader and all followers.
2. `test_multiple_writes_consistency` - Multiple writes with consistency verification using checksum comparison.
3. `test_concurrent_writes` - 20 concurrent writes to test concurrency model and verify data consistency.
4. `test_diagnostics_checksums_match` - Verify all replicas have matching checksums via `/diagnostics` endpoint.
5. `test_runtime_write_quorum_update` - Test dynamic quorum adjustment via API and verify consistency maintained.
6. `test_stores_match_after_writes` - Final consistency verification across all nodes using full store comparison.

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
- Consistency checks verify checksums match across all replicas
- Race condition detection ensures no lost updates or value mismatches

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
  - Perform data consistency checks (checksum verification)
  - Detect race conditions (value mismatches, missing keys, version drift)
  - Save results to `results/performance_results.json` including consistency reports

**`tests/test_single_quorum.py`** - Single quorum tester:

- Usage: `python tests/test_single_quorum.py <quorum_value>`
- Tests one specific quorum value
- Saves per-quorum results to `results/results_quorum_<N>.json`
- Performs comprehensive data consistency checks:
  - Checksum comparison between leader and all followers
  - Race condition detection (value mismatches, missing keys, extra keys)
  - Version consistency verification

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
  "consistency": {
    "all_consistent": true,
    "leader_keys": 10,
    "follower_keys": {"8001": 10, "8002": 10, ...}
  },
  "race_condition_check": {
    "race_conditions_detected": 0,
    "all_consistent": true,
    "race_condition_details": [],
    "version_mismatches": []
  }
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

- Monotonically (usually) increasing curve (latency vs quorum)
- May show non-linear growth due to queuing effects

![Result](results/img.png)
![Result](result.png)

Results during another runs:
![Result](result_iterations/1.png)
![Result](result_iterations/2.png)
![Result](result_iterations/3.png)
![Result](result_iterations/4.png)
![Result](result_iterations/5.png)

---

## 7. Data Consistency Verification

### 7.1 Consistency Checking Mechanisms

The system implements multiple layers of data consistency verification to ensure all replicas remain synchronized and detect any data corruption or race conditions.

#### 7.1.1 Checksum-Based Verification

**Implementation:**

- Each node (leader and followers) computes a SHA-256 checksum of its store contents
- Checksum is computed from sorted key-value pairs (JSON-serialized) to ensure deterministic results
- Checksums are exposed via `/diagnostics` and `/store` endpoints

**Verification Process:**

1. Leader computes checksum after each write operation
2. Followers compute checksum after each replication
3. Consistency checks compare leader checksum with each follower checksum
4. Mismatch indicates data inconsistency between replicas

**Usage in Tests:**

- Integration tests verify checksums match after writes
- Performance benchmarks include checksum verification after each quorum test
- Results include `consistency` field indicating whether all checksums match

#### 7.1.2 Race Condition Detection

**Implementation:**
The system performs comprehensive race condition detection by comparing full store contents across all nodes:

1. **Value Mismatch Detection:**

   - Compares each key-value pair between leader and followers
   - Detects lost updates (same key with different final values)
   - Identifies which follower has inconsistent data

2. **Missing Key Detection:**

   - Checks if all keys present in leader store exist in follower stores
   - Detects replication failures or incomplete updates

3. **Extra Key Detection:**

   - Checks if followers have keys not present in leader store
   - Detects potential data corruption or unauthorized writes

4. **Version Consistency Check:**
   - Compares version counters between leader and followers
   - Allows small drift (±1) to account for in-flight replications
   - Large version gaps indicate replication lag or failures

**Race Condition Check Results:**

```json
{
  "race_conditions_detected": 0,
  "all_consistent": true,
  "race_condition_details": [],
  "version_mismatches": [],
  "leader_key_count": 10,
  "follower_key_counts": {"8001": 10, "8002": 10, ...}
}
```

#### 7.1.3 Full Store Comparison

**Implementation:**

- Retrieves complete store contents from leader and all followers via `/store` endpoint
- Performs key-by-key and value-by-value comparison
- More thorough than checksum-only verification (identifies specific inconsistencies)

**When Used:**

- Final consistency verification in integration tests
- Post-benchmark consistency checks in performance analysis
- Detailed race condition detection

### 7.2 Consistency Verification in Tests

#### Integration Tests (`tests/test_integration.py`)

**Checksum Verification:**

- `test_diagnostics_checksums_match`: Verifies all follower checksums match leader checksum
- `test_multiple_writes_consistency`: Performs checksum comparison after multiple writes
- `test_stores_match_after_writes`: Full store comparison to verify complete consistency

**Expected Behavior:**

- All checksums should match after writes complete
- All followers should have identical key-value pairs as leader
- Version counters should be consistent (within ±1 for in-flight replications)

#### Performance Benchmarks

**Automatic Consistency Checks:**

- After each quorum test, the benchmark performs:
  1. Checksum verification via `/diagnostics` endpoint
  2. Full race condition detection via store comparison
  3. Version consistency verification

**Results Include:**

- `consistency` field: Checksum match status for each follower
- `race_condition_check` field: Detailed race condition analysis
- Both fields included in JSON results for each quorum value

### 7.3 Consistency Guarantees

**Semi-Synchronous Replication:**

- Leader waits for `WRITE_QUORUM` confirmations before acknowledging success
- Remaining replications complete in background (eventual consistency)
- With `WRITE_QUORUM=5`, all followers are guaranteed to receive updates before client acknowledgment

**Consistency Levels:**

- **Strong Consistency (WRITE_QUORUM=5)**: All replicas updated before acknowledgment
- **Eventual Consistency (WRITE_QUORUM<5)**: Some replicas may lag, but all eventually converge
- **Consistency Checks**: Verify eventual convergence has occurred

### 7.4 Interpreting Consistency Results

**All Consistent (`all_consistent: true`):**

- All checksums match
- No race conditions detected
- Version counters aligned
- System is in consistent state

**Inconsistencies Detected:**

- Checksum mismatches indicate data divergence
- Race conditions indicate lost updates or ordering issues
- Version mismatches indicate replication lag
- Investigation needed to identify root cause

**Common Causes of Inconsistencies:**

1. Network failures during replication
2. Follower failures
3. Race conditions in concurrent writes
4. Incomplete background replications
5. System load causing replication delays

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
