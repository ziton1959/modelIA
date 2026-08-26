from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer)
    actor_name = Column(String)
    action = Column(String, nullable=False)
    target = Column(String)
    details = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())