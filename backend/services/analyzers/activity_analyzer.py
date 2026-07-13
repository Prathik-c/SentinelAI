from typing import Any, Dict, List
from .base import BaseAnalyzer, IncidentData
from services.baseline_engine import BaselineStats

class ActivityAnalyzer(BaseAnalyzer):
    def analyze(self, current_state: Dict[str, Any], baseline: BaselineStats) -> List[IncidentData]:
        incidents = []
        idle_seconds = current_state.get("idle_seconds", 0.0)
        events = current_state.get("keyboard_mouse_events", 0)
        timestamp = current_state.get("timestamp", "")
        cpu = current_state.get("cpu", 0.0)
        
        # If user is deeply idle (> 15 minutes) but CPU spikes significantly
        if idle_seconds > 900 and cpu > 50.0:
            reasons = [
                f"System has been idle for {int(idle_seconds/60)} minutes.",
                f"Unexpected background activity (CPU: {cpu:.1f}%)."
            ]
            incidents.append(IncidentData(
                incident_type="unsolicited_background_activity",
                severity="medium",
                description=f"High CPU ({cpu:.1f}%) while user is idle",
                risk_score=self.calculate_risk_score(base=50, is_user_idle=True, severity_bonus=cpu/10),
                reasons=reasons,
                timestamp=timestamp,
                analyzer_name=self.name,
                cpu=cpu,
                snapshot={
                    "idle_seconds": idle_seconds
                }
            ))

        return incidents
