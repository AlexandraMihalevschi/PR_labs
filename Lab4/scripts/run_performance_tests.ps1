# PowerShell helper script to run performance tests for all quorum values
# Usage: .\run_performance_tests.ps1

Write-Host "Performance Testing Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This script will benchmark quorum values from 1 to 5."
Write-Host "Make sure 'docker compose up -d' is running first."
Write-Host ""

$testScript = Join-Path (Split-Path $PSScriptRoot -Parent) "tests\test_single_quorum.py"
$quorums = 1..5

foreach ($quorum in $quorums) {
    Write-Host ""
    Write-Host "=== Running benchmark for WRITE_QUORUM=$quorum ===" -ForegroundColor Yellow
    python $testScript $quorum
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error running test for quorum=$quorum" -ForegroundColor Red
        break
    }
}

Write-Host ""
Write-Host "All benchmarks completed. See the 'results' folder for JSON outputs." -ForegroundColor Cyan
