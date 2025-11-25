# How to Run the Key-Value Store Performance Tests

This guide explains how to run the distributed key-value store system and performance tests.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ with required packages (install via `pip install -r requirements.txt`)

## Quick Start

### 1. Start the System

Start all services (1 leader + 5 followers) with Docker Compose:

```bash
docker-compose up --build
```

**What you should see:**

- 6 containers starting up (leader + 5 followers)
- Leader listening on port 8000
- Followers listening on ports 8001-8005
- Console output showing initialization messages:
  - `Leader initialized with 5 followers`
  - `Write quorum: 3` (default)
  - `Delay range: [0.0, 1.0] seconds` (0-1000ms)

**Note:** The system uses a delay range of **[0, 1000]ms** to simulate network latency. Each replication request to a follower will have a random delay in this range.

### 2. Configure Write Quorum (Optional)

To test different quorum values, restart docker-compose with the desired value:

**On Linux/Mac (Bash):**

```bash
# Stop current containers
docker-compose down

# Start with a specific quorum value (e.g., 3)
WRITE_QUORUM=3 docker-compose up -d
```

**On Windows (PowerShell):**

```powershell
# Stop current containers
docker-compose down

# Start with a specific quorum value (e.g., 3)
$env:WRITE_QUORUM=3; docker-compose up -d
```

**Alternative (works on all platforms):**
Create a `.env` file in the project directory:

```
WRITE_QUORUM=3
```

Then run:

```bash
docker-compose up -d
```

Valid quorum values: 1, 2, 3, 4, or 5 (must be ≤ number of followers)

### 3. Run Tests

You have several options for testing:

#### Option A: Test a Single Quorum Value

**On Linux/Mac:**

```bash
# Make sure services are running with desired quorum
WRITE_QUORUM=3 docker-compose up -d

# Run test for that quorum
python test_single_quorum.py 3
```

**On Windows (PowerShell):**

```powershell
# Make sure services are running with desired quorum
$env:WRITE_QUORUM=3; docker-compose up -d

# Run test for that quorum
python test_single_quorum.py 3
```

**What you should see:**

- "Waiting for services..." message
- "Services ready!" confirmation
- "Running concurrent writes..." message
- Progress as 100 concurrent writes are executed (10 at a time)
- Results summary:
  - Average latency (in milliseconds)
  - Median latency
  - P95 and P99 latency percentiles
  - Success rate percentage
  - Total execution time
  - Consistency verification results
- Results saved to `results_quorum_3.json`

#### Option B: Test All Quorum Values (Interactive)

```bash
python run_performance_tests.py
```

**What you should see:**

- Interactive prompts for each quorum value (1-5)
- Instructions to restart docker-compose with the correct quorum
- After each test, results are saved to `results_quorum_*.json` files
- You'll need to manually restart docker-compose between tests

#### Option C: Full Automated Analysis

```bash
python performance_analysis.py
```

**What you should see:**

- Interactive prompts for each quorum value
- Performance metrics for each quorum
- A plot saved as `write_quorum_vs_latency.png`
- Consistency verification report
- Results saved to `performance_results.json`

### 4. Generate Plots from Results

If you've run tests and have `results_quorum_*.json` files:

```bash
python plot_results.py
```

**What you should see:**

- A plot showing write quorum vs average latency
- Summary statistics printed to console
- Plot saved as `write_quorum_vs_latency.png`

## Expected Results

### Performance Characteristics

With the new delay range of **[0, 1000]ms**:

1. **Higher Latency**: You should see significantly higher latencies, as each replication can now take up to 1 second.

2. **Quorum Impact**:

   - **Quorum 1**: Lowest latency (only needs 1 confirmation)
   - **Quorum 5**: Highest latency (must wait for all 5 followers)
   - Latency generally increases with quorum value

3. **With 100 Requests** (10 at a time, on 10 keys):
   - Tests will complete quickly
   - Provides meaningful statistical results
   - Easier to debug and observe behavior
   - Matches the specified test requirements

### Typical Output Example

```
Testing with WRITE_QUORUM=3
Total writes: 100, Keys: 10, Threads: 10
Waiting for services...
Services ready!
Running concurrent writes...

Results for WRITE_QUORUM=3:
  Average latency: 450.23 ms
  Median latency: 380.15 ms
  P95 latency: 850.67 ms
  P99 latency: 980.12 ms
  Success rate: 100.00%
  Total time: 5.34 seconds
  Successful writes: 100/100

Verifying data consistency...
Leader has 10 keys
Follower 8001 has 10 keys
Follower 8002 has 10 keys
Follower 8003 has 10 keys
Follower 8004 has 10 keys
Follower 8005 has 10 keys
✓ All replicas are consistent!

Results saved to results_quorum_3.json
```

### Understanding the Results

- **Average Latency**: Mean response time for write operations
- **P95/P99 Latency**: 95th/99th percentile latencies (important for understanding tail latencies)
- **Success Rate**: Percentage of writes that succeeded (should be close to 100% in normal conditions)
- **Consistency**: All followers should have the same data as the leader after writes complete

## Troubleshooting

### Services Not Starting

- Check Docker is running: `docker ps`
- Check ports 8000-8005 are not in use
- Review docker-compose logs: `docker-compose logs`

### Tests Failing

- Ensure services are running: `docker-compose ps`
- Check services are ready: `curl http://localhost:8000`
- Verify quorum value matches running services
- Check timeout values in test scripts (may need to increase for larger delays)

### High Failure Rates

- With delays up to 1000ms, some requests may timeout
- Consider increasing timeout values in test scripts
- Check network connectivity between containers

## Files Generated

After running tests, you'll have:

- `results_quorum_*.json`: Individual test results for each quorum value
- `write_quorum_vs_latency.png`: Plot showing quorum vs latency relationship
- `performance_results.json`: Full analysis results (if using performance_analysis.py)

## Next Steps

1. Run tests for multiple quorum values
2. Compare latency vs durability trade-offs
3. Analyze how delay range affects performance
4. Experiment with different request counts and thread counts
