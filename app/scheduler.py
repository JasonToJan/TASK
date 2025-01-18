from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from datetime import datetime
import logging
from app import db
from app.models import Task, TaskLog
import traceback


class TaskScheduler:
    def __init__(self, app=None):
        self.app = app
        self.logger = logging.getLogger(__name__)

        # 配置调度器
        jobstores = {
            'default': SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
        }

        executors = {
            'default': ThreadPoolExecutor(20)
        }

        job_defaults = {
            'coalesce': False,
            'max_instances': 1
        }

        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults
        )

        # 启动调度器
        try:
            self.scheduler.start()
            self.logger.info("Scheduler started successfully")
        except Exception as e:
            self.logger.error(f"Failed to start scheduler: {str(e)}")

    def add_job(self, task):
        """添加新任务到调度器"""
        job_id = f'task_{task.id}'

        try:
            self.scheduler.add_job(
                func=self._execute_task,
                trigger='cron',
                id=job_id,
                replace_existing=True,
                args=[task.id],
                **self._parse_cron(task.cron_expression)
            )
            self.logger.info(f"Job {job_id} added successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add job {job_id}: {str(e)}")
            return False

    def remove_job(self, task_id):
        """从调度器中移除任务"""
        job_id = f'task_{task_id}'
        try:
            self.scheduler.remove_job(job_id)
            self.logger.info(f"Job {job_id} removed successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to remove job {job_id}: {str(e)}")
            return False

    def update_job(self, task):
        """更新现有任务"""
        self.remove_job(task.id)
        return self.add_job(task)

    def _execute_task(self, task_id):
        """执行任务的核心函数"""
        with self.app.app_context():
            task = Task.query.get(task_id)
            if not task:
                self.logger.error(f"Task {task_id} not found")
                return

            # 创建任务日志
            log = TaskLog(
                task_id=task_id,
                start_time=datetime.utcnow(),
                status='RUNNING'
            )
            db.session.add(log)
            db.session.commit()

            try:
                # 准备执行环境
                local_vars = {}
                global_vars = {
                    '__builtins__': __builtins__,
                    'datetime': datetime,
                }

                # 执行脚本
                start_time = datetime.utcnow()
                exec(task.script_content, global_vars, local_vars)
                end_time = datetime.utcnow()

                # 更新执行状态
                execution_time = (end_time - start_time).total_seconds()
                log.status = 'SUCCESS'
                log.execution_time = execution_time
                log.end_time = end_time

                # 更新任务状态
                task.last_run = end_time
                task.last_status = 'SUCCESS'
                task.retry_count = 0

            except Exception as e:
                error_msg = traceback.format_exc()
                log.status = 'FAILED'
                log.error_message = error_msg
                log.end_time = datetime.utcnow()

                task.last_status = 'FAILED'

                # 处理重试逻辑
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    self._schedule_retry(task)

                self.logger.error(f"Task {task_id} failed: {str(e)}")

            finally:
                db.session.commit()

    def _schedule_retry(self, task):
        """安排任务重试"""
        from datetime import timedelta

        retry_delay = 5  # 5分钟后重试
        next_run = datetime.utcnow() + timedelta(minutes=retry_delay)

        self.scheduler.add_job(
            func=self._execute_task,
            trigger='date',
            run_date=next_run,
            args=[task.id],
            id=f'retry_task_{task.id}_{task.retry_count}'
        )

    def _parse_cron(self, cron_expression):
        """解析cron表达式"""
        try:
            minute, hour, day, month, day_of_week = cron_expression.split()
            return {
                'minute': minute,
                'hour': hour,
                'day': day,
                'month': month,
                'day_of_week': day_of_week
            }
        except Exception as e:
            self.logger.error(f"Failed to parse cron expression: {str(e)}")
            raise ValueError("Invalid cron expression")

