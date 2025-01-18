import os
from datetime import timedelta


class Config:
    # 基础配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard-to-guess-string'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                              'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 任务调度器配置
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = 'Asia/Shanghai'

    # 安全配置
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = timedelta(days=30)

    # 日志配置
    LOG_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'logs')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # 邮件配置（可选）
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

    # 任务配置
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'py', 'txt'}
    MAX_SCRIPT_SIZE = 1024 * 1024  # 1MB
    TASK_TIMEOUT = 3600  # 1小时
    MAX_RETRIES = 3
    RETRY_DELAY = 300  # 5分钟

    # 可选的其他调度器配置
    SCHEDULER_JOB_DEFAULTS = {
        'coalesce': False,
        'max_instances': 3
    }

    @staticmethod
    def init_app(app):
        # 确保日志目录存在
        if not os.path.exists(Config.LOG_PATH):
            os.makedirs(Config.LOG_PATH)


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    # 生产环境配置
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)

        # 配置日志处理
        import logging
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            os.path.join(cls.LOG_PATH, 'task_scheduler.log'),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(cls.LOG_FORMAT))
        file_handler.setLevel(logging.INFO)

        app.logger.addHandler(file_handler)


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
