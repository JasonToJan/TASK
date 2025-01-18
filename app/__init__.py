from flask import Flask, render_template
from config import config
import logging
from logging.handlers import RotatingFileHandler
import os
from app.extensions import db, login_manager
from app.scheduler import create_scheduler, validate_scheduler_config, TaskScheduler

# 全局scheduler实例
scheduler_instance = None


def init_scheduler_with_app(app):
    """初始化调度器的独立函数"""
    global scheduler_instance

    try:
        # 首先验证配置
        if not validate_scheduler_config(app):
            app.logger.error("Invalid scheduler configuration")
            return None

        # 检查现有实例
        if scheduler_instance and hasattr(scheduler_instance, 'scheduler'):
            if scheduler_instance.scheduler.running:
                app.logger.info('Using existing scheduler instance')
                return scheduler_instance
            else:
                app.logger.info('Existing scheduler not running, creating new instance')
                try:
                    scheduler_instance.shutdown()
                except:
                    pass

        # 创建新实例
        with app.app_context():
            new_scheduler = create_scheduler(app)
            if new_scheduler and new_scheduler.scheduler.running:
                scheduler_instance = new_scheduler
                app.logger.info('New scheduler instance created and running')

                # 验证调度器状态
                try:
                    jobs = scheduler_instance.scheduler.get_jobs()
                    app.logger.info(f'Current scheduled jobs: {len(jobs)}')
                except Exception as e:
                    app.logger.error(f'Error checking scheduler jobs: {str(e)}')

                return scheduler_instance
            else:
                app.logger.error('Failed to create new scheduler instance')
                return None

    except Exception as e:
        app.logger.error(f'Scheduler initialization failed: {str(e)}', exc_info=True)
        return None


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)

    # 配置日志
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler(
            'logs/task_scheduler.log',
            maxBytes=10240,
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.DEBUG)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.DEBUG)
        app.logger.info('Task Scheduler startup')

    # 注册蓝图
    from app.views import bp as tasks_bp
    from app.auth import auth_bp
    app.register_blueprint(tasks_bp)
    app.register_blueprint(auth_bp)

    # 创建数据库表
    with app.app_context():
        db.create_all()

    # 初始化任务调度器
    if not app.config.get('TESTING'):
        scheduler = init_scheduler_with_app(app)
        if scheduler:
            app.scheduler = scheduler
        else:
            app.logger.error('Failed to initialize scheduler')

    # 注册清理函数
    @app.teardown_appcontext
    def shutdown_scheduler(exception=None):
        global scheduler_instance
        if scheduler_instance and hasattr(scheduler_instance, 'scheduler'):
            try:
                if scheduler_instance.scheduler.running:
                    scheduler_instance.scheduler.shutdown(wait=True)
                    app.logger.info('Task Scheduler shut down successfully')
            except Exception as e:
                app.logger.error(f'Error shutting down scheduler: {str(e)}')

    # 添加健康检查路由
    @app.route('/health')
    def health_check():
        from flask import jsonify
        status = {
            'status': 'healthy',
            'scheduler_running': False,
            'scheduler_status': None
        }

        if scheduler_instance and hasattr(scheduler_instance, 'scheduler'):
            status['scheduler_running'] = scheduler_instance.scheduler.running
            status['scheduler_status'] = scheduler_instance.get_scheduler_status()

        return jsonify(status)

    @app.context_processor
    def utility_processor():
        def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
            if value:
                return value.strftime(format)
            return ''

        return dict(format_datetime=format_datetime)

    @app.shell_context_processor
    def make_shell_context():
        return {
            'db': db,
            'scheduler': scheduler_instance,
            'TaskScheduler': TaskScheduler,
            'init_scheduler': init_scheduler_with_app  # 添加初始化函数到shell上下文
        }

    return app


def get_scheduler():
    """获取当前调度器实例"""
    global scheduler_instance
    from flask import current_app

    if not scheduler_instance or not getattr(scheduler_instance, 'scheduler', None):
        return init_scheduler_with_app(current_app)

    if not scheduler_instance.scheduler.running:
        current_app.logger.warning("Scheduler not running, attempting to reinitialize...")
        return init_scheduler_with_app(current_app)

    return scheduler_instance
