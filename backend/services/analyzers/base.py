import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from services.baseline_engine import BaselineStats

@dataclass
class IncidentData:
    """
    A single detected anomaly as a structured Python object.
    """
    incident_type: str
    severity: str
    description: str
    risk_score: float
    reasons: List[str]
    timestamp: str
    analyzer_name: str
    process_name: Optional[str] = None
    cpu: Optional[float] = None
    ram: Optional[float] = None
    snapshot: Optional[Dict[str, Any]] = field(default=None)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class BaseAnalyzer:
    """
    Abstract base class for all Behaviour Engine analyzers.
    """
    
    @property
    def name(self) -> str:
        return self.__class__.__name__

    def analyze(self, current_state: Dict[str, Any], baseline: BaselineStats) -> List[IncidentData]:
        """
        Analyzes the current system state against the baseline.
        Must return a list of IncidentData (empty if no anomalies).
        """
        raise NotImplementedError

    def calculate_risk_score(
        self,
        base: float,
        is_user_idle: bool = False,
        is_unusual_hour: bool = False,
        is_unknown: bool = False,
        severity_bonus: float = 0.0,
    ) -> float:
        """
        Helper to calculate a 0-100 risk score based on context.
        """
        score = base
        if is_user_idle:
            score += 15
        if is_unusual_hour:
            score += 10
        if is_unknown:
            score += 20
        score += min(severity_bonus, 20)
        return min(round(score, 1), 100.0)
