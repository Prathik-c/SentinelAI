from typing import Any, Dict, List
from .base import BaseAnalyzer, IncidentData
from services.baseline_engine import BaselineStats


class DriftAnalyzer(BaseAnalyzer):
    """
    Detects long-term behavioural drift by comparing the current in-memory
    baseline against the oldest persisted BaselineSnapshot.

    FIX: No longer opens its own SQLAlchemy session.
    It receives the session from the caller (incident_engine.run_anomaly_check)
    which owns the session lifecycle — preventing connection pool leaks.
    """

    def analyze(self, current_state: Dict[str, Any], baseline: BaselineStats) -> List[IncidentData]:
        incidents = []
        timestamp = current_state.get("timestamp", "")

        # Retrieve the session injected via current_state (set by incident_engine)
        db = current_state.get("_db_session")
        if db is None:
            return incidents  # No session available — skip silently

        try:
            from models.tables import BaselineSnapshot
            oldest_snapshot = (
                db.query(BaselineSnapshot)
                .order_by(BaselineSnapshot.computed_at.asc())
                .first()
            )
            if not oldest_snapshot:
                return incidents

            cpu_drift = baseline.cpu_mean - oldest_snapshot.cpu_mean
            ram_drift = baseline.ram_mean - oldest_snapshot.ram_mean

            if cpu_drift > 15.0:
                incidents.append(IncidentData(
                    incident_type="behavioural_drift_cpu",
                    severity="low",
                    description="Slow upward drift in average CPU utilization detected",
                    risk_score=self.calculate_risk_score(base=25),
                    reasons=[
                        f"Your baseline CPU usage has slowly increased from "
                        f"{oldest_snapshot.cpu_mean:.1f}% to {baseline.cpu_mean:.1f}%.",
                        "This indicates a gradual change in system workload over weeks."
                    ],
                    timestamp=timestamp,
                    analyzer_name=self.name,
                    cpu=baseline.cpu_mean,
                    snapshot={
                        "old_cpu_mean": oldest_snapshot.cpu_mean,
                        "current_cpu_mean": baseline.cpu_mean
                    }
                ))

            if ram_drift > 20.0:
                incidents.append(IncidentData(
                    incident_type="behavioural_drift_ram",
                    severity="low",
                    description="Slow upward drift in average RAM utilization detected",
                    risk_score=self.calculate_risk_score(base=25),
                    reasons=[
                        f"Your baseline RAM usage has slowly increased from "
                        f"{oldest_snapshot.ram_mean:.1f}% to {baseline.ram_mean:.1f}%.",
                        "This suggests more persistent background applications are running over time."
                    ],
                    timestamp=timestamp,
                    analyzer_name=self.name,
                    ram=baseline.ram_mean,
                    snapshot={
                        "old_ram_mean": oldest_snapshot.ram_mean,
                        "current_ram_mean": baseline.ram_mean
                    }
                ))

        except Exception as exc:
            from loguru import logger
            logger.error(f"DriftAnalyzer query failed: {exc}")

        return incidents
