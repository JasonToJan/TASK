from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from flask import current_app
import logging
from app.models import Task, TaskLog
from app.extensions import db
from datetime import datetime

# 全局调度器实例
scheduler = None

def get_scheduler():
    """获取调度器实例"""
    global scheduler
    return scheduler

def execute_task(task_id):
    """任务执行函数"""
    # 获取应用上下文
    app = current_app._get_current_object()

    with app.app_context():
        try:
            # 获取任务信息
            task = Task.query.get(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")

            # 创建任务日志
            task_log = TaskLog(
                task_id=task_id,
                start_time=datetime.now(),
                status='running'
            )
            db.session.add(task_log)
            db.session.commit()

            try:
                # 执行脚本
                local_vars = {}
                exec(task.script_content, {}, local_vars)

                # 如果脚本定义了main函数，则执行它
                if 'main' in local_vars and callable(local_vars['main']):
                    result = local_vars['main']()
                else:
                    result = "Script executed successfully"

                # 更新任务日志
                task_log.status = 'completed'
                task_log.result = str(result)
                task_log.end_time = datetime.now()

            except Exception as e:
                # 记录执行错误
                task_log.status = 'failed'
                task_log.result = str(e)
                task_log.end_time = datetime.now()
                app.logger.error(f"Task {task_id} execution failed: {str(e)}")

            finally:
                # 保存任务日志
                db.session.commit()

        except Exception as e:
            app.logger.error(f"Task {task_id} failed: {str(e)}")
            raise


class TaskScheduler:
    def __init__(self, app=None):
        self.app = app
        self.logger = logging.getLogger(__name__)

        if not app:
            raise ValueError("Flask app instance is required")

        # 配置调度器
        try:
            jobstores = {
                'default': SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
            }

            executors = {
                'default': ThreadPoolExecutor(20)
            }

            job_defaults = {
                'coalesce': False,
                'max_instances': 1,
                'misfire_grace_time': None
            }

            self.scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults
            )

            # 设置全局调度器实例
            global scheduler
            scheduler = self.scheduler

            # 注册应用上下文
            self.app = app

            # 启动调度器
            self.scheduler.start()

            # 验证调度器是否正常运行
            if not self.scheduler.running:
                raise RuntimeError("Scheduler failed to start")

            self.logger.info("Scheduler started successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize scheduler: {str(e)}")
            raise

    def add_job(self, task):
        """添加新任务到调度器"""
        job_id = f'task_{task.id}'

        try:
            # 先检查cron表达式是否有效
            cron_kwargs = self._parse_cron(task.cron_expression)

            # 检查调度器状态
            if not self.scheduler.running:
                self.logger.error("Scheduler is not running")
                return False

            # 添加任务，确保在应用上下文中执行
            self.scheduler.add_job(
                func=execute_task,  # 使用execute_task函数
                trigger='cron',
                id=job_id,
                replace_existing=True,
                args=[task.id],  # 传递任务ID作为参数
                **cron_kwargs
            )

            self.logger.info(f"Job {job_id} added successfully")
            return True
        except ValueError as ve:
            self.logger.error(f"Invalid cron expression for job {job_id}: {str(ve)}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to add job {job_id}: {str(e)}")
            return False

    def remove_job(self, task_id):
        """从调度器中移除任务"""
        job_id = f'task_{task_id}'
        try:
            if self.scheduler and self.scheduler.running:
                self.scheduler.remove_job(job_id)
                self.logger.info(f"Job {job_id} removed successfully")
                return True
            else:
                self.logger.error("Scheduler is not running")
                return False
        except Exception as e:
            self.logger.error(f"Failed to remove job {job_id}: {str(e)}")
            return False

    def update_job(self, task):
        """更新现有任务"""
        return self.remove_job(task.id) and self.add_job(task)

    def _parse_cron(self, cron_expression):
        """解析cron表达式"""
        try:
            parts = cron_expression.split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts
                return {
                    'minute': minute,
                    'hour': hour,
                    'day': day,
                    'month': month,
                    'day_of_week': day_of_week
                }
            elif len(parts) == 6:
                second, minute, hour, day, month, day_of_week = parts
                return {
                    'second': second,
                    'minute': minute,
                    'hour': hour,
                    'day': day,
                    'month': month,
                    'day_of_week': day_of_week
                }
            else:
                raise ValueError("Unsupported cron expression format")
        except Exception as e:
            self.logger.error(f"Failed to parse cron expression: {str(e)}")
            raise ValueError(f"Invalid cron expression: {str(e)}")

    def shutdown(self):
        """关闭调度器"""
        try:
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown()
                self.logger.info("Scheduler shutdown successfully")
        except Exception as e:
            self.logger.error(f"Failed to shutdown scheduler: {str(e)}")
            raise

def init_scheduler(app):
    """初始化调度器"""
    try:
        global scheduler
        if scheduler is None:
            scheduler_instance = TaskScheduler(app)
            return scheduler_instance
        return None
    except Exception as e:
        app.logger.error(f"Failed to initialize scheduler: {str(e)}")
        return None