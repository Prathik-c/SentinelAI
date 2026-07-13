from typing import Any, Dict, List
from .base import BaseAnalyzer, IncidentData
from services.baseline_engine import BaselineStats

class ResourceAnalyzer(BaseAnalyzer):
    def analyze(self, current_state: Dict[str, Any], baseline: BaselineStats) -> List[IncidentData]:
        incidents = []
        cpu = current_state.get("cpu", 0.0)
        ram = current_state.get("ram", 0.0)
        idle_seconds = current_state.get("idle_seconds", 0.0)
        timestamp = current_state.get("timestamp", "")
        
        is_idle = idle_seconds > 300

        # CPU Spike check
        cpu_threshold = baseline.cpu_mean + (3 * baseline.cpu_std) if baseline.cpu_std > 0 else 80.0
        cpu_threshold = min(max(cpu_threshold, 60.0), 95.0) # Sane limits

        if cpu > cpu_threshold:
            severity = "critical" if cpu > 85 else "high"
            base_score = 70 if severity == "critical" else 50
            deviation = cpu - baseline.cpu_mean

            reasons = [
                f"CPU at {cpu:.1f}% — your normal average is {baseline.cpu_mean:.1f}%",
                f"Exceeds dynamic threshold of {cpu_threshold:.1f}% based on your typical usage",
            ]
            if is_idle:
                reasons.append("User appears idle — unexpected background CPU usage")

            incidents.append(IncidentData(
                incident_type="cpu_spike",
                severity=severity,
                description=f"CPU spike: {cpu:.1f}%",
                risk_score=self.calculate_risk_score(base=base_score, is_user_idle=is_idle, severity_bonus=deviation / 5),
                reasons=reasons,
                timestamp=timestamp,
                analyzer_name=self.name,
                cpu=cpu,
                snapshot={
                    "cpu_mean": baseline.cpu_mean,
                    "cpu_std": baseline.cpu_std,
                    "cpu_threshold": cpu_threshold
                }
            ))

        # RAM Spike check
        ram_threshold = baseline.ram_mean + (2 * baseline.ram_std) if baseline.ram_std > 0 else 90.0
        ram_threshold = min(max(ram_threshold, 70.0), 95.0)

        if ram > ram_threshold:
            severity = "high" if ram > 90 else "medium"
            deviation = ram - baseline.ram_mean
            reasons = [
                f"RAM at {ram:.1f}% — your normal average is {baseline.ram_mean:.1f}%",
                f"Exceeds dynamic threshold of {ram_threshold:.1f}%",
            ]
            if is_idle:
                reasons.append("User appears idle — unexpected memory pressure")

            incidents.append(IncidentData(
                incident_type="ram_spike",
                severity=severity,
                description=f"RAM spike: {ram:.1f}%",
                risk_score=self.calculate_risk_score(base=45, is_user_idle=is_idle, severity_bonus=deviation / 5),
                reasons=reasons,
                timestamp=timestamp,
                analyzer_name=self.name,
                ram=ram,
                snapshot={
                    "ram_mean": baseline.ram_mean,
                    "ram_std": baseline.ram_std,
                    "ram_threshold": ram_threshold
                }
            ))

        return incidents
