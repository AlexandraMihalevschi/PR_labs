#!/usr/bin/env bash
set -euo pipefail

echo "Performance Testing Script"
echo "========================================"
echo "This script benchmarks write quorum values from 1 to 5."
echo "Make sure 'docker compose up -d' is running first."
echo

TEST_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/tests/test_single_quorum.py"

for quorum in 1 2 3 4 5; do
    echo
    echo "=== Running benchmark for WRITE_QUORUM=${quorum} ==="
    python "$TEST_SCRIPT" "$quorum"
done

echo
echo "All benchmarks completed. JSON outputs are under results/."

