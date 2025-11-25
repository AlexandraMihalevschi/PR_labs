# Key-Value Store with Single-Leader Replication

A distributed key-value store implementation with single-leader replication using semi-synchronous replication. The leader accepts writes and replicates them to followers concurrently, waiting for a configurable number of confirmations (write quorum) before reporting success.

## Features

- **Single-leader replication**: Only the leader accepts writes
- **Semi-synchronous replication**: Leader waits for a configurable write quorum
- **Concurrent execution**: All requests are processed concurrently via asyncio/FastAPI
- **Network lag simulation**: Randomized replication delay (default 10–200 ms) per follower
- **Docker-based deployment**: One leader and 5 followers in separate containers
- **Integrity signals**: Every node exposes a checksum/integrity sign to prove data parity
- **REST API**: JSON-based communication via FastAPI

## Architecture

- **Leader**: Accepts write requests, replicates to followers, waits for quorum
- **Followers**: Receive replication requests and store data locally
- **Write Quorum**: Configurable number of follower confirmations required (1-5)

## Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for running tests locally)

### Running the System

1. **Start all services**:

   ```bash
   docker compose up --build -d
   ```

2. **Configure write quorum** (optional, default is 3):

   **Linux/Mac:**

   ```bash
   WRITE_QUORUM=3 docker compose up -d
   ```

   **Windows (PowerShell):**

   ```powershell
   $env:WRITE_QUORUM=3; docker compose up -d
   ```

3. **Configure network delay** (optional, default is 10–200ms):

   **Linux/Mac:**

   ```bash
   MIN_DELAY=0.01 MAX_DELAY=0.2 docker compose up -d
   ```

   **Windows (PowerShell):**

   ```powershell
   $env:MIN_DELAY=0.01; $env:MAX_DELAY=0.2; docker compose up -d
   ```

The services will be available at:

- Leader: http://localhost:8000
- Followers: http://localhost:8001-8005

## API Endpoints

### Leader Endpoints

- `GET /` - Health check
- `POST /set` - Write a key-value pair
  ```json
  {
    "key": "my_key",
    "value": "my_value"
  }
  ```
- `GET /get/{key}` - Read a value
- `GET /store` - Get entire store plus checksum/version (for verification)
- `GET /diagnostics` - Compact stats (checksum, quorum state, integrity sign)
- `POST /config/write_quorum` - Update quorum at runtime (still defaults via env var)

### Follower Endpoints

- `GET /` - Health check
- `POST /replicate` - Receive replication request (internal)
- `GET /get/{key}` - Read a value from replica
- `GET /store` - Get entire store plus checksum/version
- `GET /diagnostics` - Quick integrity sign + checksum (used by tests/scripts)

## Testing

### Integration Tests

Run the integration tests to verify the system works correctly:

```bash
# Make sure services are running
docker compose up -d

# Run tests
pytest tests/test_integration.py -v
```

Or run the module directly:

```bash
python tests/test_integration.py
```

### Performance Analysis

Helper scripts now live under `scripts/` and rely on the runtime `/config/write_quorum` API, so you no longer need to restart containers between runs.

1. **Single quorum benchmark**

   ```bash
   python tests/test_single_quorum.py 3
   ```

   This performs ~100 writes (10 concurrent on 10 keys) and emits a JSON file under `results/`.

2. **Sequential benchmarks for quorum=1..5**

   ```bash
   python scripts/run_performance_tests.py
   # or
   pwsh scripts/run_performance_tests.ps1
   # or
   bash scripts/run_performance_tests.sh
   ```

   Each run drops a `results/results_quorum_<n>.json`.

3. **Full analysis + plotting + checksum verification**

   ```bash
   python scripts/performance_analysis.py
   ```

   This sweeps quorum values, measures average/percentile latency, generates `results/write_quorum_vs_latency.png`, writes `results/performance_results.json`, and prints an explanation of why higher quorums increase latency. Use `python scripts/plot_results.py` to regenerate plots from existing JSON files.

## Environment Variables

### Leader

- `PORT`: Port to listen on (default: 8000)
- `FOLLOWERS`: Comma-separated list of follower URLs
- `WRITE_QUORUM`: Number of follower confirmations required (default: 3)
- `MIN_DELAY`: Minimum replication delay in seconds (default: 0.01 ≈ 10 ms)
- `MAX_DELAY`: Maximum replication delay in seconds (default: 0.2 ≈ 200 ms)
- `FOLLOWER_TIMEOUT`: HTTP timeout when contacting followers (default: 2.5s)

### Followers

- `PORT`: Port to listen on (8001-8005)
- `FOLLOWER_ID`: Identifier for the follower

## Performance Analysis Results

The performance analysis will show:

1. **Write Quorum vs Latency**: As the write quorum increases, latency typically increases because the leader must wait for more confirmations. However, higher quorum provides better durability guarantees.

2. **Data Consistency**: After all writes complete, the system verifies that all followers have the same data as the leader. With proper quorum settings, all replicas should be consistent.

## Example Usage

```python
import httpx
import asyncio

async def example():
    async with httpx.AsyncClient() as client:
        # Write a key
        response = await client.post(
            "http://localhost:8000/set",
            json={"key": "test", "value": "hello"}
        )
        print(response.json())

        # Read from leader
        response = await client.get("http://localhost:8000/get/test")
        print(response.json())

        # Read from follower
        response = await client.get("http://localhost:8001/get/test")
        print(response.json())

asyncio.run(example())
```

## Implementation Details

- **Semi-synchronous replication**: Leader writes locally first, then replicates to all followers concurrently. It waits for `WRITE_QUORUM` confirmations before returning success. If quorum is not met, the write is rolled back.

- **Network lag simulation**: Each replication request to a follower includes a random delay between `MIN_DELAY` and `MAX_DELAY` (default: 0-1000ms) to simulate real network conditions.

- **Concurrent execution**: All replication requests are sent concurrently using `asyncio.gather()`, so delays differ for each follower.

- **Error handling**: If a follower fails to replicate, it's counted as a failed replication. The write succeeds only if enough followers confirm (meeting the quorum).
