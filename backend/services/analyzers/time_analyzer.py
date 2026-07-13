from typing import Any, Dict, List
from .base import BaseAnalyzer, IncidentData
from services.baseline_engine import BaselineStats

class TimeAnalyzer(BaseAnalyzer):
    def analyze(self, current_state: Dict[str, Any], baseline: BaselineStats) -> List[IncidentData]:
        incidents = []
        cpu = current_state.get("cpu", 0.0)
        hour = current_state.get("hour", 0)
        timestamp = current_state.get("timestamp", "")
        
        hp = baseline.hourly_patterns.get(hour)
        if hp is None:
            return incidents
            
        # If this hour is usually very idle (low cpu) but now it's high
        if hp.avg_cpu < 10.0 and cpu > 40.0:
            reasons = [
                f"High activity at {hour:02d}:xx — historically, this hour averages {hp.avg_cpu:.1f}% CPU.",
                f"Current CPU is {cpu:.1f}%, which is highly unusual for this time of day."
            ]
            incidents.append(IncidentData(
                incident_type="unusual_time_activity",
                severity="medium",
                description=f"Unusual activity at {hour:02d}:xx",
                risk_score=self.calculate_risk_score(base=40, is_unusual_hour=True, severity_bonus=cpu/10),
                reasons=reasons,
                timestamp=timestamp,
                analyzer_name=self.name,
                cpu=cpu,
                snapshot={
                    "hour": hour,
                    "hourly_avg_cpu": hp.avg_cpu
                }
            ))
            
        return incidents
