from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from database import Base

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, server_default=func.now())
    type = Column(String, default="face")
    severity = Column(String, default="medium")
    description = Column(String)
    snapshot = Column(String, nullable=True)
    status = Column(String, default="pending")
    approved_at = Column(DateTime, nullable=True)
    report = Column(String, nullable=True)