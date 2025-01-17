from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import json
import logging
import subprocess
from pathlib import Path
from croniter import croniter, CroniterNotAlphaError

from app.database.database import get_db
from app.models import task as models
from app.schemas import task as schemas
from app.config.config import settings
from app.core.scheduler import scheduler

router = APIRouter()

# 获取任务列表
@router.get("/tasks/", response_model=List[schemas.Task])
async def get_tasks(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None
):
    """获取任务列表"""
    query = db.query(models.Task)
    if is_active is not None:
        query = query.filter(models.Task.is_active == is_active)
    tasks = query.offset(skip).limit(limit).all()
    return tasks

# 获取单个任务
@router.get("/tasks/{task_id}", response_model=schemas.Task)
async def get_task(task_id: int, db: Session = Depends(get_db)):
    """获取单个任务的详细信息"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

# 创建任务
@router.post("/tasks/", response_model=schemas.Task)
async def create_task(
    task: schemas.TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """创建新任务"""
    try:
        # 1. 验证脚本路径
        if not settings.validate_script_path(task.script_path):
            raise HTTPException(
                status_code=400,
                detail="Invalid script path"
            )

        # 2. 验证和解析调度配置
        try:
            schedule_config = json.loads(task.schedule_config)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid schedule configuration format"
            )

        # 3. 验证调度类型和配置
        try:
            next_run_time = calculate_next_run_time(task.schedule_type, schedule_config)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e)
            )

        # 4. 检查任务名称是否重复
        existing_task = db.query(models.Task).filter(
            models.Task.name == task.name
        ).first()
        if existing_task:
            raise HTTPException(
                status_code=400,
                detail="Task name already exists"
            )

        # 5. 创建任务记录
        db_task = models.Task(
            name=task.name,
            description=task.description,
            script_path=task.script_path,
            schedule_type=task.schedule_type,
            schedule_config=task.schedule_config,
            is_active=task.is_active,
            next_run_time=next_run_time,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        try:
            db.add(db_task)
            db.commit()
            db.refresh(db_task)
        except Exception as e:
            db.rollback()
            logging.error(f"Database error while creating task: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to create task in database"
            )

        # 6. 如果任务是活动的，添加到调度器
        if db_task.is_active:
            try:
                background_tasks.add_task(
                    add_task_to_scheduler,
                    db_task,
                    db
                )
            except Exception as e:
                logging.error(f"Scheduler error: {str(e)}")
                db_task.is_active = False
                db.commit()
                raise HTTPException(
                    status_code=500,
                    detail="Failed to add task to scheduler"
                )

        return db_task

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error while creating task: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


# 辅助函数
def calculate_next_run_time(schedule_type: str, config: dict) -> datetime:
    """计算下次运行时间"""
    now = datetime.now()

    if schedule_type == "interval":
        if not all(key in config for key in ["days", "hours", "minutes"]):
            raise ValueError("Interval configuration must include days, hours, and minutes")

        delta = timedelta(
            days=config.get("days", 0),
            hours=config.get("hours", 0),
            minutes=config.get("minutes", 0)
        )

        if delta.total_seconds() < 60:  # 最小间隔1分钟
            raise ValueError("Interval must be at least 1 minute")

        return now + delta

    elif schedule_type == "cron":
        if "expression" not in config:
            raise ValueError("Cron configuration must include expression")

        try:
            cron = croniter(config["expression"], now)
            return cron.get_next(datetime)
        except CroniterNotAlphaError:
            raise ValueError("Invalid cron expression")

    elif schedule_type == "fixed":
        if "datetime" not in config:
            raise ValueError("Fixed schedule must include datetime")

        try:
            run_time = datetime.fromisoformat(config["datetime"])
            if run_time <= now:
                raise ValueError("Fixed schedule datetime must be in the future")
            return run_time
        except ValueError as e:
            raise ValueError(f"Invalid datetime format: {str(e)}")

    else:
        raise ValueError("Invalid schedule type")


def add_task_to_scheduler(task: models.Task, db: Session):
    """添加任务到调度器"""
    try:
        job_id = f"task_{task.id}"

        # 如果任务已存在，先移除
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

            # 准备调度参数
        schedule_config = json.loads(task.schedule_config)

        if task.schedule_type == "interval":
            scheduler.add_job(
                execute_task,
                'interval',
                days=schedule_config.get("days", 0),
                hours=schedule_config.get("hours", 0),
                minutes=schedule_config.get("minutes", 0),
                id=job_id,
                args=[task.id],
                next_run_time=task.next_run_time
            )

        elif task.schedule_type == "cron":
            scheduler.add_job(
                execute_task,
                'cron',
                id=job_id,
                args=[task.id],
                **croniter.expand(schedule_config["expression"])
            )

        elif task.schedule_type == "fixed":
            scheduler.add_job(
                execute_task,
                'date',
                id=job_id,
                args=[task.id],
                run_date=datetime.fromisoformat(schedule_config["datetime"])
            )

    except Exception as e:
        logging.error(f"Error adding task {task.id} to scheduler: {str(e)}")
        raise

    # 更新任务


@router.put("/tasks/{task_id}", response_model=schemas.Task)
async def update_task(
        task_id: int,
        task_update: schemas.TaskUpdate,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db)
):
    """更新任务"""
    db_task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        update_data = task_update.dict(exclude_unset=True)

        # 验证脚本路径
        if "script_path" in update_data:
            if not settings.validate_script_path(update_data["script_path"]):
                raise HTTPException(status_code=400, detail="Invalid script path")

                # 验证调度配置
        if "schedule_config" in update_data:
            try:
                schedule_config = json.loads(update_data["schedule_config"])
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid schedule configuration")

                # 如果更新了调度相关的配置，重新计算下次运行时间
        if "schedule_type" in update_data or "schedule_config" in update_data:
            schedule_type = update_data.get("schedule_type", db_task.schedule_type)
            schedule_config = json.loads(
                update_data.get("schedule_config", db_task.schedule_config)
            )
            update_data["next_run_time"] = calculate_next_run_time(
                schedule_type,
                schedule_config
            )

            # 更新任务记录
        for key, value in update_data.items():
            setattr(db_task, key, value)

        db_task.updated_at = datetime.now()

        try:
            db.commit()
            db.refresh(db_task)
        except Exception as e:
            db.rollback()
            logging.error(f"Database error while updating task: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to update task")

            # 更新调度器
        if db_task.is_active:
            background_tasks.add_task(add_task_to_scheduler, db_task, db)
        else:
            job_id = f"task_{task_id}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

        return db_task

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating task: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# 执行任务的核心函数
async def execute_task(task_id: int):
    """执行任务"""
    db = SessionLocal()
    try:
        # 获取任务信息
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            logging.error(f"Task {task_id} not found")
            return

            # 创建任务历史记录
        history = models.TaskHistory(
            task_id=task_id,
            status="running",
            start_time=datetime.now()
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        try:
            # 构建脚本完整路径
            script_path = settings.scripts_dir / task.script_path

            # 执行脚本
            process = subprocess.Popen(
                ["python", str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            try:
                stdout, stderr = process.communicate(
                    timeout=settings.scripts["max_execution_time"]
                )

                if process.returncode == 0:
                    status = "success"
                    error = None
                else:
                    status = "failed"
                    error = stderr

            except subprocess.TimeoutExpired:
                process.kill()
                status = "timeout"
                stdout, stderr = process.communicate()
                error = "Task execution timed out"

                # 更新历史记录
            history.status = status
            history.output = stdout
            history.error = error
            history.end_time = datetime.now()

            # 更新任务的最后运行时间
            task.last_run_time = history.start_time

            # 如果是固定时间任务且已执行完成，设置为非活动
            if task.schedule_type == "fixed":
                task.is_active = False

                # 更新下次运行时间
            if task.is_active:
                schedule_config = json.loads(task.schedule_config)
                task.next_run_time = calculate_next_run_time(
                    task.schedule_type,
                    schedule_config
                )

            db.commit()

        except Exception as e:
            logging.error(f"Error executing task {task_id}: {str(e)}")
            history.status = "failed"
            history.error = str(e)
            history.end_time = datetime.now()
            db.commit()

    except Exception as e:
        logging.error(f"Error in execute_task: {str(e)}")
    finally:
        db.close()

    # 手动执行任务


@router.post("/tasks/{task_id}/execute")
async def manual_execute_task(
        task_id: int,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db)
):
    """手动执行任务"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    background_tasks.add_task(execute_task, task_id)
    return {"message": "Task execution started"}


# 批量操作任务
@router.post("/tasks/batch")
async def batch_operation(
        operation: schemas.BatchOperation,
        db: Session = Depends(get_db)
):
    """批量操作任务（暂停/恢复/删除）"""
    try:
        tasks = db.query(models.Task).filter(
            models.Task.id.in_(operation.task_ids)
        ).all()

        if not tasks:
            raise HTTPException(status_code=404, detail="No tasks found")

        for task in tasks:
            job_id = f"task_{task.id}"

            if operation.action == "pause":
                task.is_active = False
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)

            elif operation.action == "resume":
                task.is_active = True
                add_task_to_scheduler(task, db)

            elif operation.action == "delete":
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
                db.delete(task)

        db.commit()
        return {"message": f"Batch {operation.action} completed"}

    except Exception as e:
        db.rollback()
        logging.error(f"Error in batch operation: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # 获取任务历史记录


@router.get("/tasks/{task_id}/history", response_model=List[schemas.TaskHistory])
async def get_task_history(
        task_id: int,
        db: Session = Depends(get_db),
        skip: int = 0,
        limit: int = 100
):
    """获取任务的执行历史记录"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    histories = db.query(models.TaskHistory) \
        .filter(models.TaskHistory.task_id == task_id) \
        .order_by(models.TaskHistory.start_time.desc()) \
        .offset(skip) \
        .limit(limit) \
        .all()

    return histories


# 清理任务历史记录
@router.delete("/tasks/{task_id}/history")
async def clean_task_history(
        task_id: int,
        db: Session = Depends(get_db),
        days: Optional[int] = 30
):
    """清理指定天数之前的任务历史记录"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        db.query(models.TaskHistory) \
            .filter(
            models.TaskHistory.task_id == task_id,
            models.TaskHistory.start_time < cutoff_date
        ) \
            .delete()

        db.commit()
        return {"message": f"History records older than {days} days have been cleaned"}

    except Exception as e:
        db.rollback()
        logging.error(f"Error cleaning task history: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to clean history records")

    # 删除任务


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    """删除任务"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        # 从调度器中移除任务
        job_id = f"task_{task_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

            # 删除任务及其历史记录
        db.delete(task)
        db.commit()

        return {"message": "Task deleted successfully"}

    except Exception as e:
        db.rollback()
        logging.error(f"Error deleting task: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete task")