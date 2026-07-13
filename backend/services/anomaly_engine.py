"""
SentinelAI — Behaviour Engine Coordinator

Coordinates multiple independent analyzers to detect anomalies based on learned behaviours.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger

from services.baseline_engine import BaselineStats
from services.analyzers import (
    ResourceAnalyzer,
    ProcessAnalyzer,
    TimeAnalyzer,
    ActivityAnalyzer,
    StartupAnalyzer,
    DriftAnalyzer,
    IncidentData
)

# Initialize analyzers
_analyzers = [
    ResourceAnalyzer(),
    ProcessAnalyzer(),
    TimeAnalyzer(),
    ActivityAnalyzer(),
    StartupAnalyzer(),
    DriftAnalyzer()
]

def detect_anomalies(
    cpu: float,
    ram: float,
    disk: float,
    idle_seconds: float,
    top_processes: Optional[List[Dict[str, Any]]],
    baseline: BaselineStats,
    keyboard_mouse_events: int = 0,
    foreground_app: str = "",
    db_session: Any = None,
) -> List[IncidentData]:
    """
    Runs all analyzers against the current system state.
    """
    now = datetime.utcnow()
    
    current_state = {
        "cpu": cpu,
        "ram": ram,
        "disk": disk,
        "idle_seconds": idle_seconds,
        "top_processes": top_processes or [],
        "timestamp": now.isoformat(),
        "hour": now.hour,
        "keyboard_mouse_events": keyboard_mouse_events,
        "foreground_app": foreground_app,
        "_db_session": db_session,  # Injected for analyzers that need DB access (e.g. DriftAnalyzer)
    }

    all_incidents: List[IncidentData] = []
    
    for analyzer in _analyzers:
        try:
            incidents = analyzer.analyze(current_state, baseline)
            all_incidents.extend(incidents)
        except Exception as exc:
            logger.error(f"Analyzer {analyzer.name} failed: {exc}")
            
    if all_incidents:
        logger.info(f"Behaviour Engine found {len(all_incidents)} anomalies.")
    else:
        logger.debug("Behaviour Engine: system normal.")
        
    return all_incidents
