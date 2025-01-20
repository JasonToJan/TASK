import logging
import time
from datetime import datetime
import pytz
from flask import current_app
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from app import db
from app.models import Task, TaskLog

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 在文件开头添加
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

class SchedulerError(Exception):
    """调度器异常"""
    pass


def validate_scheduler_config(app):
    """验证调度器配置"""
    required_configs = [
        'SQLALCHEMY_DATABASE_URI',
        'SCHEDULER_TIMEZONE',
        'SCHEDULER_MAX_WORKERS',
    ]

    for config in required_configs:
        if config not in app.config:
            app.logger.error(f"Missing required configuration: {config}")
            return False

    return True


def create_scheduler(app):
    """创建调度器工厂函数"""
    try:
        scheduler = TaskScheduler()
        scheduler.init_app(app)
        return scheduler
    except Exception as e:
        app.logger.error(f"Failed to create scheduler: {e}", exc_info=True)
        return None


def get_scheduler():
    """
    获取或创建调度器实例
    Returns:
        TaskScheduler: 调度器实例或None
    """
    from flask import current_app

    # 添加详细的日志记录
    current_app.logger.debug("Attempting to get scheduler instance")

    # 首先尝试从应用实例获取
    if hasattr(current_app, 'scheduler'):
        current_app.logger.debug("Found scheduler attribute in current_app")
        scheduler = current_app.scheduler

        if scheduler:
            current_app.logger.debug("Scheduler instance exists")
            if hasattr(scheduler, 'scheduler'):
                current_app.logger.debug("Scheduler has internal scheduler attribute")
                if scheduler.scheduler.running:
                    current_app.logger.debug("Scheduler is running, returning existing instance")
                    return scheduler
                else:
                    current_app.logger.warning("Found scheduler but it's not running")
            else:
                current_app.logger.warning("Scheduler instance missing internal scheduler")
        else:
            current_app.logger.warning("Scheduler attribute is None")
    else:
        current_app.logger.warning("No scheduler attribute found in current_app")

    # 尝试重新初始化
    try:
        current_app.logger.info("Attempting to reinitialize scheduler")

        # 首先验证配置
        if not validate_scheduler_config(current_app):
            current_app.logger.error("Invalid scheduler configuration")
            return None

        # 创建新的调度器实例
        scheduler = TaskScheduler()
        scheduler.init_app(current_app)

        # 验证新创建的调度器
        if scheduler and hasattr(scheduler, 'scheduler') and scheduler.scheduler.running:
            current_app.logger.info("Successfully created new scheduler instance")
            # 保存到应用上下文
            current_app.scheduler = scheduler
            return scheduler
        else:
            current_app.logger.error("Failed to create valid scheduler instance")
            return None

    except Exception as e:
        current_app.logger.error(f"Error reinitializing scheduler: {e}", exc_info=True)
        return None

def execute_task_wrapper(task_id):
    """
    包装任务执行函数，确保在 Flask 应用上下文中运行
    """
    from app import flask_app  # 延迟导入
    with flask_app.app_context():  # 添加括号，正确使用上下文
        logger.info(f"Executing task {task_id} within Flask application context")
        return execute_task(task_id)


def execute_task(task_id):
    """
    全局任务执行函数 - 动态共享所有依赖，执行任务脚本。
    """
    try:
        with current_app.app_context():
            logger.info(f"Starting execution of task {task_id}")

            task = Task.query.get(task_id)
            if not task:
                logger.error(f"Task {task_id} not found.")
                return "Task not found", 'FAILED'

            task_log = TaskLog(
                task_id=task_id,
                start_time=datetime.now(BEIJING_TZ),
                status='RUNNING'
            )
            db.session.add(task_log)
            db.session.commit()
            start_time = time.time()

            log_output = ""
            error_message = None
            status = 'FAILED'
            try:
                if not task.script_content:
                    raise ValueError("Script content is empty")

                # 捕获脚本标准输出
                import io
                import sys

                output_buffer = io.StringIO()
                original_stdout = sys.stdout
                sys.stdout = output_buffer  # 重定向标准输出

                # 构建动态执行环境（统一作用域）
                exec_scope = globals().copy()
                exec_scope.update(sys.modules)
                exec_scope['__builtins__'] = __builtins__

                try:
                    logger.info(f"Executing script for task {task_id}")
                    exec(task.script_content, exec_scope, exec_scope)  # 使用统一作用域
                    status = 'SUCCESS'
                    log_output = output_buffer.getvalue()
                except Exception as script_exec_error:
                    status = 'FAILED'
                    log_output = output_buffer.getvalue()
                    error_message = str(script_exec_error)
                    logger.error(f"Failed to execute task {task_id}: {script_exec_error}")
                finally:
                    sys.stdout = original_stdout

            except Exception as general_error:
                error_message = str(general_error)
                log_output = f"Execution error: {error_message}"
                logger.error(f"Task execution failed: {general_error}")
                if task.max_retries > task.retry_count:
                    task.retry_count += 1
                    db.session.commit()
                    logger.info(f"Retrying task {task_id}, attempt {task.retry_count}/{task.max_retries}")

            finally:
                end_time = time.time()
                execution_time = end_time - start_time

                try:
                    task_log.end_time = datetime.now(BEIJING_TZ)
                    task_log.status = status
                    task_log.log_output = log_output
                    task_log.error_message = error_message
                    task_log.execution_time = execution_time

                    task.last_run = datetime.now(BEIJING_TZ)
                    task.last_status = status

                    db.session.commit()
                    logger.info(f"Task {task_id} completed with status {status}")
                except Exception as log_update_error:
                    logger.error(f"Failed to update task log: {log_update_error}")
                    db.session.rollback()

            return log_output, status
    except Exception as system_error:
        logger.error(f"System error during task execution: {system_error}")
        return f"System error: {str(system_error)}", 'FAILED'






class TaskScheduler:
    def __init__(self, app=None):
        """初始化调度器"""
        self.app = app
        self.scheduler = None
        self.logger = logger
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """初始化调度器并与Flask应用绑定"""
        self.app = app
        self.logger = app.logger

        try:
            # 配置任务存储
            jobstores = {
                'default': SQLAlchemyJobStore(
                    url=app.config['SQLALCHEMY_DATABASE_URI'],
                    engine_options={'pool_recycle': 3600}
                )
            }

            # 配置执行器
            executors = {
                'default': ThreadPoolExecutor(
                    max_workers=app.config.get('SCHEDULER_MAX_WORKERS', 20)
                )
            }

            # 任务默认值
            job_defaults = {
                'coalesce': app.config.get('SCHEDULER_COALESCE', False),
                'max_instances': app.config.get('SCHEDULER_MAX_INSTANCES', 1),
                'misfire_grace_time': app.config.get('SCHEDULER_MISFIRE_GRACE_TIME', 3600)
            }

            # 创建调度器
            self.scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone=BEIJING_TZ  # 直接使用北京时区
            )

            # 添加事件监听器
            self.scheduler.add_listener(
                self._job_event_listener,
                EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
            )

            # 启动调度器
            if not self.scheduler.running:
                self.scheduler.start()
                time.sleep(1)  # 等待调度器完全启动

                if not self.scheduler.running:
                    raise RuntimeError("Scheduler failed to start")

                self.logger.info("Scheduler started successfully")

                # 加载所有活动任务
                self._load_all_tasks()

        except Exception as e:
            self.logger.error(f"Failed to initialize scheduler: {e}", exc_info=True)
            raise

    def get_scheduler_status(self):
        """获取调度器状态信息"""
        try:
            if not self.scheduler:
                return {
                    'state': 'not_initialized',
                    'running': False,
                    'job_count': 0
                }

            return {
                'state': 'running' if self.scheduler.running else 'stopped',
                'running': self.scheduler.running,
                'job_count': len(self.scheduler.get_jobs()),
                'next_run': min([job.next_run_time for job in self.scheduler.get_jobs() if job.next_run_time],
                                default=None)
            }
        except Exception as e:
            self.logger.error(f"Error getting scheduler status: {e}")
            return {
                'state': 'error',
                'error': str(e),
                'running': False
            }

    def _load_all_tasks(self):
        """加载所有活动的任务"""
        try:
            with self.app.app_context():
                active_tasks = Task.query.filter_by(is_active=True).all()
                for task in active_tasks:
                    self.add_job(task)
                self.logger.info(f"Loaded {len(active_tasks)} active tasks")
        except Exception as e:
            self.logger.error(f"Failed to load tasks: {e}", exc_info=True)

    def _job_event_listener(self, event):
        """任务执行事件监听器"""
        if event.exception:
            self.logger.error(f"Job {event.job_id} failed: {event.exception}")
        else:
            self.logger.info(f"Job {event.job_id} executed successfully")

    def _parse_schedule(self, task):
        try:
            if task.schedule_type == 'once':
                if not task.schedule_config or 'datetime' not in task.schedule_config:
                    raise ValueError("Missing datetime for one-time schedule")

                    # 解析时间并转换为北京时间
                dt = datetime.fromisoformat(task.schedule_config['datetime'])
                if not dt.tzinfo:
                    dt = BEIJING_TZ.localize(dt)
                elif dt.tzinfo != BEIJING_TZ:
                    dt = dt.astimezone(BEIJING_TZ)

                    # 与当前北京时间比较
                if dt < datetime.now(BEIJING_TZ):
                    raise ValueError("Scheduled time is in the past")
                return {'trigger': 'date', 'run_date': dt}

            else:
                # cron表达式部分保持不变
                cron_parts = task.cron_expression.strip().split()
                if len(cron_parts) not in [5, 6]:
                    raise ValueError("Invalid cron expression")

                fields = ['minute', 'hour', 'day', 'month', 'day_of_week']
                cron_kwargs = dict(zip(fields, cron_parts))

                if len(cron_parts) == 6:
                    cron_kwargs['year'] = cron_parts[5]

                return {'trigger': 'cron', **cron_kwargs}

        except Exception as e:
            raise ValueError(f"Schedule parsing failed: {str(e)}")

    def add_job(self, task):
        """添加新任务到调度器"""
        try:
            self._check_scheduler()

            job_id = f'task_{task.id}'
            self.logger.info(f"Adding job {job_id} ({task.name})")

            # 解析调度配置
            try:
                schedule_kwargs = self._parse_schedule(task)
            except ValueError as e:
                self.logger.error(f"Schedule parsing failed for task {task.id}: {e}. Config: {task.schedule_config}")
                return False

            # 移除现有任务（如果存在）
            if self.scheduler.get_job(job_id):
                self.logger.info(f"Removing existing job {job_id}")
                try:
                    self.scheduler.remove_job(job_id)
                except Exception as e:
                    self.logger.error(f"Failed to remove existing job {job_id}: {e}", exc_info=True)

            # 添加新任务
            try:
                from flask import current_app
                job = self.scheduler.add_job(
                    func=execute_task_wrapper,
                    args=[task.id],
                    id=job_id,
                    name=task.name,
                    replace_existing=True,
                    misfire_grace_time=task.timeout,
                    **schedule_kwargs
                )

                if job and (job.next_run_time or schedule_kwargs['trigger'] == 'date'):
                    self.logger.info(f"Job {job_id} added successfully. Next run at: {job.next_run_time}")
                    return True
                else:
                    self.logger.error(f"Job {job_id} failed to schedule properly")
                    return False

            except Exception as e:
                self.logger.error(f"Failed to add job {job_id}: {e}", exc_info=True)
                return False

        except Exception as e:
            self.logger.error(f"Unexpected error in add_job: {e}", exc_info=True)
            return False

    def remove_job(self, task_id):
        """从调度器中移除任务"""
        try:
            self._check_scheduler()
            job_id = f'task_{task_id}'

            try:
                self.scheduler.remove_job(job_id)
                self.logger.info(f"Job {job_id} removed successfully")
                return True
            except Exception as e:
                self.logger.warning(f"Job {job_id} not found or already removed: {e}")
                return True  # 如果任务不存在也返回成功

        except Exception as e:
            self.logger.error(f"Failed to remove job: {e}", exc_info=True)
            return False

    def update_job(self, task):
        """更新现有任务"""
        try:
            self._check_scheduler()

            job_id = f'task_{task.id}'
            self.logger.info(f"Updating job {job_id} ({task.name})")

            # 获取当前任务状态
            old_job = self.scheduler.get_job(job_id)
            old_job_state = None
            if old_job:
                old_job_state = {
                    'next_run_time': old_job.next_run_time,
                    'trigger': old_job.trigger
                }

            # 如果任务处于活动状态，更新调度
            if task.is_active:
                success = self.add_job(task)
                if not success:
                    if old_job_state:
                        self._restore_job(task, old_job_state)
                    return False
            else:
                # 如果任务被禁用，移除调度
                self.remove_job(task.id)

            return True

        except Exception as e:
            self.logger.error(f"Failed to update job: {e}", exc_info=True)
            return False

    def _restore_job(self, task, old_state):
        """恢复任务到原状态"""
        try:
            job_id = f'task_{task.id}'
            self.scheduler.add_job(
                func=execute_task,
                args=[task.id],
                trigger=old_state['trigger'],
                next_run_time=old_state['next_run_time'],
                id=job_id,
                name=task.name,
                replace_existing=True
            )
            self.logger.info(f"Successfully restored job {job_id} to previous state")
        except Exception as e:
            self.logger.error(f"Failed to restore job {job_id}: {e}")

    def pause_job(self, task_id):
        """暂停任务"""
        try:
            self._check_scheduler()
            job_id = f'task_{task_id}'

            job = self.scheduler.get_job(job_id)
            if job:
                self.scheduler.pause_job(job_id)
                self.logger.info(f"Job {job_id} paused")
                return True
            return False

        except Exception as e:
            self.logger.error(f"Failed to pause job: {e}", exc_info=True)
            return False

    def resume_job(self, task_id):
        """恢复任务"""
        try:
            self._check_scheduler()
            job_id = f'task_{task_id}'

            job = self.scheduler.get_job(job_id)
            if job:
                self.scheduler.resume_job(job_id)
                self.logger.info(f"Job {job_id} resumed")
                return True
            return False

        except Exception as e:
            self.logger.error(f"Failed to resume job: {e}", exc_info=True)
            return False

    def get_job_info(self, task_id):
        """获取任务运行状态信息"""
        try:
            self._check_scheduler()
            job_id = f'task_{task_id}'

            job = self.scheduler.get_job(job_id)
            if not job:
                return None

            return {
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time,
                'trigger': str(job.trigger),
                'pending': job.pending
            }

        except Exception as e:
            self.logger.error(f"Failed to get job info: {e}", exc_info=True)
            return None

    def get_all_jobs(self):
        """获取所有任务的运行状态"""
        try:
            self._check_scheduler()
            jobs = []
            for job in self.scheduler.get_jobs():
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time,
                    'trigger': str(job.trigger),
                    'pending': job.pending
                })
            return jobs

        except Exception as e:
            self.logger.error(f"Failed to get all jobs: {e}", exc_info=True)
            return []

    def _check_scheduler(self):
        """检查调度器状态"""
        if not self.scheduler:
            raise SchedulerError("Scheduler not initialized")
        if not self.scheduler.running:
            raise SchedulerError("Scheduler not running")

    def shutdown(self):
        """关闭调度器"""
        if self.scheduler and self.scheduler.running:
            try:
                self.scheduler.shutdown(wait=True)
                self.logger.info("Scheduler shutdown complete")
            except Exception as e:
                self.logger.error(f"Scheduler shutdown error: {e}", exc_info=True)

    def run_job_now(self, task_id):
        try:
            self._check_scheduler()
            job_id = f'task_{task_id}'

            job = self.scheduler.get_job(job_id)
            if job:
                # 使用北京时间
                self.scheduler.modify_job(job_id, next_run_time=datetime.now(BEIJING_TZ))
                self.logger.info(f"Job {job_id} scheduled for immediate execution")
                return True
            return False

        except Exception as e:
            self.logger.error(f"Failed to run job now: {e}", exc_info=True)
            return False

