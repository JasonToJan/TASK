from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import config
import logging
from logging.handlers import RotatingFileHandler
import os

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'


def create_app(config_name='default'):
    app = Flask(__name__)
    # 使用配置字典获取对应的配置类
    app.config.from_object(config[config_name])

    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)

    # 注册蓝图
    from app.views import bp as tasks_bp
    from app.auth import auth_bp
    app.register_blueprint(tasks_bp)
    app.register_blueprint(auth_bp)

    # 配置日志
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/task_scheduler.log',
                                         maxBytes=10240,
                                         backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('Task Scheduler startup')

    # 创建数据库表
    with app.app_context():
        db.create_all()

    # 初始化任务调度器
    if not app.config.get('TESTING'):  # 测试环境不初始化调度器
        if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            try:
                from app.views import init_scheduler, scheduler
                with app.app_context():
                    init_scheduler(app)
                    app.logger.info('Task Scheduler initialized successfully')

                    # 注册清理函数
                    @app.teardown_appcontext
                    def shutdown_scheduler(exception=None):
                        if scheduler:
                            try:
                                scheduler.shutdown()
                                app.logger.info('Task Scheduler shut down successfully')
                            except Exception as e:
                                app.logger.error(f'Error shutting down scheduler: {str(e)}')

            except Exception as e:
                app.logger.error(f'Failed to initialize scheduler: {str(e)}')
                if app.debug:
                    print(f'Scheduler initialization error: {str(e)}')

    # 添加上下文处理器
    @app.context_processor
    def utility_processor():
        def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
            if value:
                return value.strftime(format)
            return ''
        return dict(format_datetime=format_datetime)

    return app


from app import models  # 这行必须在最后
