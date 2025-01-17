from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.database import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    description = Column(Text, nullable=True)
    script_path = Column(String(255))
    schedule_type = Column(String(50))  # interval, cron, or fixed
    schedule_config = Column(Text)  # JSON string
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    last_run_time = Column(DateTime, nullable=True)
    next_run_time = Column(DateTime, nullable=True)

    histories = relationship("TaskHistory", back_populates="task", cascade="all, delete-orphan")

class TaskHistory(Base):
    __tablename__ = "task_histories"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    start_time = Column(DateTime, default=datetime.now)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(50))  # running, success, failed, timeout
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    task = relationship("Task", back_populates="histories")