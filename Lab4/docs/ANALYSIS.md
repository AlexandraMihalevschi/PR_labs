# Performance Analysis: Write Quorum vs Latency

## Test Configuration

- **Total writes**: 100 concurrent writes
- **Concurrency**: 10 writes at a time (10 threads)
- **Number of keys**: 10 keys (each key written ~10 times)
- **Write quorum values tested**: 1, 2, 3, 4, 5
- **Network delay range**: [0ms, 1000ms] (random delay per replication)
- **Replication**: Concurrent (all followers receive requests simultaneously)

## Expected Results: Write Quorum vs Average Latency

### Explanation

As the **write quorum** increases, the **average latency** should generally **increase**. Here's why:

1. **Quorum = 1**: The leader only needs to wait for 1 follower to confirm. Since replication requests are sent concurrently to all 5 followers, the leader can return success as soon as the fastest follower responds (which could be as fast as 0ms, or up to 1000ms depending on the random delay).

2. **Quorum = 2**: The leader must wait for 2 followers to confirm. This means waiting for the second-fastest follower to respond. The latency will be higher than quorum=1 because we need to wait for two confirmations.

3. **Quorum = 3**: The leader must wait for 3 followers (majority). This is typically the sweet spot for durability vs performance.

4. **Quorum = 4**: The leader must wait for 4 followers. Higher latency as we need more confirmations.

5. **Quorum = 5**: The leader must wait for all 5 followers. This provides maximum durability but highest latency, as we must wait for the slowest follower (which could take up to 1000ms).

### Mathematical Model

With concurrent replication and random delays in [0, 1000ms]:

- **Quorum = k**: Latency ≈ k-th smallest delay among 5 random delays
- As k increases, we're waiting for progressively slower responses
- Expected latency increases roughly proportionally with quorum value

### Expected Plot Shape

The plot should show:

- **Increasing trend**: Higher quorum → Higher latency
- **Non-linear relationship**: The increase may not be perfectly linear due to:
  - Random delay distribution
  - Network variability
  - Concurrent execution effects
- **Variability**: With random delays, there will be variance in measurements

## Data Consistency Results

### Expected Outcome

After all writes complete, **all replicas should match the leader** if:

- All writes succeeded (quorum was met)
- No network failures occurred
- The system is functioning correctly

### Explanation

1. **Semi-synchronous replication**: The leader only reports success after receiving the required number of confirmations (write quorum). This ensures that:

   - At least `WRITE_QUORUM` followers have the data
   - The write is durable (survives up to `5 - WRITE_QUORUM` follower failures)

2. **Consistency guarantee**:

   - **Quorum = 1-3**: Not all followers may have all data immediately (eventual consistency)
   - **Quorum = 4-5**: All or most followers should have all data (stronger consistency)

3. **Why consistency might vary**:

   - With **quorum < 5**: Some followers might not receive all writes if they're slow
   - However, since we're testing with successful writes, all followers should eventually receive the data
   - The consistency check runs after all writes complete, giving time for replication

4. **Expected consistency results**:
   - **Quorum = 1**: May show some inconsistencies (only 1 follower guaranteed to have data)
   - **Quorum = 2-3**: Most followers should be consistent
   - **Quorum = 4-5**: All followers should be consistent (all or majority have all data)

### Trade-offs

- **Lower quorum (1-2)**:

  - ✅ Lower latency
  - ✅ Better performance
  - ❌ Lower durability (fewer replicas guaranteed)
  - ❌ Weaker consistency guarantees

- **Higher quorum (4-5)**:

  - ✅ Higher durability (more replicas guaranteed)
  - ✅ Stronger consistency
  - ❌ Higher latency
  - ❌ Worse performance

- **Quorum = 3** (majority):
  - ✅ Good balance between durability and performance
  - ✅ Can tolerate 2 follower failures
  - ✅ Reasonable latency

## Running the Analysis

1. **Start the system**:

   ```bash
   docker-compose up --build
   ```

2. **Test each quorum value**:

   **Linux/Mac:**

   ```bash
   # Test quorum 1
   WRITE_QUORUM=1 docker-compose up -d
   python test_single_quorum.py 1

   # Test quorum 2
   WRITE_QUORUM=2 docker-compose up -d
   python test_single_quorum.py 2

   # ... repeat for quorum 3, 4, 5
   ```

   **Windows (PowerShell):**

   ```powershell
   # Test quorum 1
   $env:WRITE_QUORUM=1; docker-compose up -d
   python test_single_quorum.py 1

   # Test quorum 2
   $env:WRITE_QUORUM=2; docker-compose up -d
   python test_single_quorum.py 2

   # ... repeat for quorum 3, 4, 5
   ```

3. **Generate the plot**:

   ```bash
   python plot_results.py
   ```

4. **Review results**:
   - Check `results_quorum_*.json` files for detailed metrics
   - View `write_quorum_vs_latency.png` for the visualization
   - Review consistency reports in the JSON files

## Interpreting Your Results

When you run the tests, compare your actual results to these expectations:

1. **Latency trend**: Does latency increase with quorum? (It should)
2. **Latency values**: Are they in the expected range given [0-1000ms] delays?
3. **Consistency**: Do all followers match the leader? (May vary by quorum)
4. **Success rate**: Should be close to 100% if system is healthy

Use these insights to understand the trade-offs between durability, consistency, and performance in distributed systems!
