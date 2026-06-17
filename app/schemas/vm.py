from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

class VMCreate(BaseModel):
    name: str
    template: str
    config: Optional[Dict[str, Any]] = {}

class VMOut(BaseModel):
    id: int
    name: str
    status: str
    owner_id: int
    template: str
    config: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True