from models.tables import Incident
from sqlalchemy.orm import Session

def create_incident(db: Session, description: str, snapshot: str = None, severity: str = "medium"):
    incident = Incident(
        type="face",
        severity=severity,
        description=description,
        snapshot=snapshot,
        status="pending"
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident

def get_all_incidents(db: Session):
    return db.query(Incident).order_by(Incident.timestamp.desc()).all()

def update_incident_status(db: Session, incident_id: int, status: str):
    from sqlalchemy.sql import func
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if incident:
        incident.status = status
        if status == "approved":
            incident.approved_at = func.now()
        db.commit()
        db.refresh(incident)
    return incident