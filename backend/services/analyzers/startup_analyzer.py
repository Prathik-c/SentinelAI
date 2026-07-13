import sys
import psutil
from typing import Any, Dict, List
from .base import BaseAnalyzer, IncidentData
from services.baseline_engine import BaselineStats

# Conditionally import winreg for Windows environments
if sys.platform == "win32":
    import winreg
else:
    winreg = None

class StartupAnalyzer(BaseAnalyzer):
    def get_current_startup_items(self) -> List[str]:
        items = []
        if not winreg:
            return items
            
        # HKCU Run
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                for i in range(winreg.QueryInfoKey(key)[1]):
                    name, _, _ = winreg.EnumValue(key, i)
                    items.append(f"HKCU\\Run\\{name}")
        except Exception:
            pass
            
        # HKLM Run
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                for i in range(winreg.QueryInfoKey(key)[1]):
                    name, _, _ = winreg.EnumValue(key, i)
                    items.append(f"HKLM\\Run\\{name}")
        except Exception:
            pass
            
        return items

    def get_current_services(self) -> List[str]:
        services = []
        if sys.platform != "win32":
            return services
            
        try:
            for svc in psutil.win_service_iter():
                services.append(svc.name())
        except Exception:
            pass
        return services

    def analyze(self, current_state: Dict[str, Any], baseline: BaselineStats) -> List[IncidentData]:
        incidents = []
        timestamp = current_state.get("timestamp", "")
        
        # Load baseline startup patterns
        known_startup = []
        if baseline.startup_patterns:
            try:
                import json
                known_startup = json.loads(baseline.startup_patterns)
            except Exception:
                pass
        
        if not known_startup:
            return incidents

        current_startup_items = self.get_current_startup_items()
        current_services = self.get_current_services()

        new_startup = [item for item in current_startup_items if item not in known_startup]
        new_services = [svc for svc in current_services if svc not in known_startup]

        for item in new_startup:
            parts = item.split('\\')
            item_name = parts[-1] if parts else item
            incidents.append(IncidentData(
                incident_type="new_startup_application",
                severity="high",
                description=f"New startup application detected: {item_name}",
                risk_score=self.calculate_risk_score(base=60, is_unknown=True),
                reasons=[
                    f"Startup item '{item}' was not present in the behavioral baseline.",
                    "Malicious software often configures itself to start automatically on boot."
                ],
                timestamp=timestamp,
                analyzer_name=self.name,
                process_name=item,
                snapshot={"item": item}
            ))

        for svc in new_services:
            incidents.append(IncidentData(
                incident_type="new_windows_service",
                severity="medium",
                description=f"New Windows service detected: {svc}",
                risk_score=self.calculate_risk_score(base=45, is_unknown=True),
                reasons=[
                    f"Service '{svc}' is not part of the established baseline services.",
                    "A new background service has been registered on the system."
                ],
                timestamp=timestamp,
                analyzer_name=self.name,
                process_name=svc,
                snapshot={"service": svc}
            ))

        return incidents
