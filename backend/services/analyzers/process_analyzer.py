from typing import Any, Dict, List
from .base import BaseAnalyzer, IncidentData
from services.baseline_engine import BaselineStats
from config import KNOWN_PROCESS_THRESHOLD

class ProcessAnalyzer(BaseAnalyzer):
    def analyze(self, current_state: Dict[str, Any], baseline: BaselineStats) -> List[IncidentData]:
        incidents = []
        processes = current_state.get("top_processes", [])
        idle_seconds = current_state.get("idle_seconds", 0.0)
        timestamp = current_state.get("timestamp", "")
        hour = current_state.get("hour", 0)
        
        is_idle = idle_seconds > 300
        seen_unknown = set()

        for proc in processes:
            name = proc.get("name", "").strip()
            cpu = float(proc.get("cpu", 0.0))
            ram = float(proc.get("ram", 0.0))

            if not name or cpu < 2.0:
                continue

            # Check for unknown process
            if not baseline.is_process_known(name, KNOWN_PROCESS_THRESHOLD):
                if name not in seen_unknown and cpu >= 5.0:
                    hp = baseline.hourly_patterns.get(hour)
                    is_odd_hr = hp is not None and hp.avg_cpu < 5.0 and cpu > 20.0
                    
                    reasons = [
                        f"'{name}' has never been seen in your system history",
                        f"Currently using {cpu:.1f}% CPU and {ram:.1f}% RAM",
                    ]
                    if is_idle:
                        reasons.append("Running while user is idle — potentially unsolicited")
                    if is_odd_hr:
                        reasons.append(f"Unusual to have high CPU at hour {hour:02d}:xx for this system")

                    incidents.append(IncidentData(
                        incident_type="unknown_process",
                        severity="high",
                        description=f"Unknown process '{name}' using {cpu:.1f}% CPU",
                        risk_score=self.calculate_risk_score(base=55, is_user_idle=is_idle, is_unusual_hour=is_odd_hr, is_unknown=True, severity_bonus=cpu/10),
                        reasons=reasons,
                        timestamp=timestamp,
                        analyzer_name=self.name,
                        process_name=name,
                        cpu=cpu,
                        ram=ram,
                        snapshot={
                            "known_process_count": len(baseline.known_processes)
                        }
                    ))
                    seen_unknown.add(name)
                continue # Skip resource checks if unknown

            # Check for high resource known process
            ps = baseline.known_processes.get(name)
            if ps and ps.avg_cpu >= 1.0:
                ratio = cpu / ps.avg_cpu
                if ratio >= 3.0 and cpu >= 10.0:
                    reasons = [
                        f"'{name}' is using {cpu:.1f}% CPU — normally uses {ps.avg_cpu:.1f}%",
                        f"That's {ratio:.1f}x its typical resource consumption",
                    ]
                    incidents.append(IncidentData(
                        incident_type="high_resource_process",
                        severity="medium",
                        description=f"'{name}' spiked to {cpu:.1f}% CPU (normally {ps.avg_cpu:.1f}%)",
                        risk_score=self.calculate_risk_score(base=35, severity_bonus=cpu/20),
                        reasons=reasons,
                        timestamp=timestamp,
                        analyzer_name=self.name,
                        process_name=name,
                        cpu=cpu,
                        snapshot={
                            "process_avg_cpu": ps.avg_cpu,
                            "process_max_cpu": ps.max_cpu
                        }
                    ))

        return incidents
