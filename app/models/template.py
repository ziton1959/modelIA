from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON
from datetime import datetime
from app.database import Base


class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    os = Column(String, nullable=False)
    packages = Column(JSON, default=[])
    packer_spec = Column(JSON, default={})
    ansible_roles = Column(JSON, default=[])
    is_cached = Column(Boolean, default=False)
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
