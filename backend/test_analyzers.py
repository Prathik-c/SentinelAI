# pyrefly: ignore [missing-import]
import pytest
from datetime import datetime
from unittest.mock import patch
from services.baseline_engine import BaselineStats, ProcessStats, HourlyPattern
from services.anomaly_engine import detect_anomalies

@patch('services.analyzers.startup_analyzer.StartupAnalyzer.get_current_startup_items', return_value=["HKCU\\Run\\safe_app"])
@patch('services.analyzers.startup_analyzer.StartupAnalyzer.get_current_services', return_value=[])
def test_detect_anomalies(mock_services, mock_startup):
    # Setup dummy baseline
    baseline = BaselineStats(
        sample_count=100,
        cpu_mean=10.0,
        cpu_std=2.0,
        ram_mean=40.0,
        ram_std=5.0,
        disk_mean=30.0,
        cpu_threshold=16.0,
        ram_threshold=50.0,
        known_processes={
            "chrome.exe": ProcessStats(
                name="chrome.exe",
                count=50,
                avg_cpu=5.0,
                avg_ram=10.0,
                max_cpu=15.0,
                first_seen="2026-07-10T12:00:00",
                last_seen="2026-07-10T12:00:00"
            )
        },
        hourly_patterns={
            12: HourlyPattern(hour=12, avg_cpu=10.0, avg_ram=40.0, avg_idle=100.0, sample_count=10)
        },
        daily_patterns={},
        process_graph={"chrome.exe": ["chrome_child.exe"]},
        activity_patterns={"avg_idle": 300.0, "avg_events": 50},
        startup_patterns='["HKCU\\\\Run\\\\safe_app"]',
        computed_at=datetime.utcnow().isoformat()
    )

    # 1. Test normal state
    incidents = detect_anomalies(
        cpu=12.0,
        ram=42.0,
        disk=30.0,
        idle_seconds=10.0,
        top_processes=[{"name": "chrome.exe", "cpu": 4.0, "ram": 8.0, "pid": 123, "ppid": 99}],
        baseline=baseline
    )
    assert len(incidents) == 0

    # 2. Test CPU spike
    incidents_cpu = detect_anomalies(
        cpu=80.0,
        ram=42.0,
        disk=30.0,
        idle_seconds=10.0,
        top_processes=[],
        baseline=baseline
    )
    assert len(incidents_cpu) > 0
    assert any(inc.incident_type == "cpu_spike" for inc in incidents_cpu)

    # 3. Test unknown process
    incidents_proc = detect_anomalies(
        cpu=12.0,
        ram=42.0,
        disk=30.0,
        idle_seconds=10.0,
        top_processes=[{"name": "unknown_miner.exe", "cpu": 15.0, "ram": 2.0, "pid": 456, "ppid": 1}],
        baseline=baseline
    )
    assert len(incidents_proc) > 0
    assert any(inc.incident_type == "unknown_process" for inc in incidents_proc)
