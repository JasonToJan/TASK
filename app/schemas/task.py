from pydantic import BaseModel, validator
from typing import Optional, List
from datetime import datetime
import json

class TaskBase(BaseModel):
    name: str
    description: Optional[str] = None
    script_path: str
    schedule_type: str
    schedule_config: str
    is_active: bool = True

    @validator('schedule_type')
    def validate_schedule_type(cls, v):
        if v not in ['interval', 'cron', 'fixed']:
            raise ValueError('Invalid schedule type')
        return v

    @validator('schedule_config')
    def validate_schedule_config(cls, v):
        try:
            json.loads(v)
        except json.JSONDecodeError:
            raise ValueError('Invalid JSON format in schedule_config')
        return v

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    script_path: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_config: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('schedule_type')
    def validate_schedule_type(cls, v):
        if v is not None and v not in ['interval', 'cron', 'fixed']:
            raise ValueError('Invalid schedule type')
        return v

    @validator('schedule_config')
    def validate_schedule_config(cls, v):
        if v is not None:
            try:
                json.loads(v)
            except json.JSONDecodeError:
                raise ValueError('Invalid JSON format in schedule_config')
        return v

class TaskHistory(BaseModel):
    id: int
    task_id: int
    start_time: datetime
    end_time: Optional[datetime]
    status: str
    output: Optional[str]
    error: Optional[str]

    class Config:
        orm_mode = True

class Task(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_run_time: Optional[datetime]
    next_run_time: Optional[datetime]
    histories: List[TaskHistory] = []

    class Config:
        orm_mode = True

class BatchOperation(BaseModel):
    action: str
    task_ids: List[int]

    @validator('action')
    def validate_action(cls, v):
        if v not in ['pause', 'resume', 'delete']:
            raise ValueError('Invalid action')
        return v