from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from datetime import datetime
from app.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)
    status = Column(String, default="queued")
    owner_id = Column(Integer, ForeignKey("users.id"))
    vm_id = Column(Integer, ForeignKey("vms.id"), nullable=True)
    logs = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
