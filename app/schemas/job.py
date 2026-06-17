from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class JobCreate(BaseModel):
    type: str
    vm_id: Optional[int] = None

class JobOut(BaseModel):
    id: int
    type: str
    status: str
    owner_id: int
    vm_id: Optional[int]
    logs: str
    created_at: datetime
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True