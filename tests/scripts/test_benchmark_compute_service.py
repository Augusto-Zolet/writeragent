# WriterAgent - Benchmark Compute Service Tests
# Copyright (c) 2026 KeithCu
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from scripts.benchmark_compute_service import (
    WORKLOADS,
    BenchmarkResult,
    ManagedBenchmarkServer,
    format_results_table,
    run_benchmark_scenario,
    run_benchmarks,
)


def test_workloads_defined() -> None:
    assert "numpy_vector" in WORKLOADS
    assert "tabular_stats" in WORKLOADS
    assert "pure_python" in WORKLOADS
    assert "stateful_session" in WORKLOADS


def test_benchmark_result_percentiles() -> None:
    res = BenchmarkResult(
        workload="numpy_vector",
        concurrency=2,
        total_requests=4,
        successful_requests=4,
        failed_requests=0,
        duration_sec=0.1,
        rps=40.0,
        latencies_ms=[10.0, 20.0, 30.0, 40.0],
    )
    assert res.mean_ms == 25.0
    assert res.p50_ms == 30.0
    assert res.max_ms == 40.0

    table = format_results_table([res])
    assert "numpy_vector" in table
    assert "40.0" in table


def test_managed_server_and_scenario_run() -> None:
    with ManagedBenchmarkServer(max_threads=4) as base_url:
        res = run_benchmark_scenario(
            target_url=base_url,
            workload_key="pure_python",
            concurrency=2,
            requests_per_worker=2,
        )
        assert res.total_requests == 4
        assert res.successful_requests == 4
        assert res.failed_requests == 0
        assert res.rps > 0.0


def test_run_benchmarks_quick() -> None:
    # numpy_vector needs NumPy inside isolated execute; the CI worker often
    # has no numpy, so the "quick" path uses the same pure_python workload as
    # test_managed_server_and_scenario_run.
    results = run_benchmarks(
        workloads=["pure_python"],
        concurrencies=[1, 2],
        requests_per_worker=2,
        server_threads=4,
    )
    assert len(results) == 2
    assert all(r.failed_requests == 0 for r in results)
