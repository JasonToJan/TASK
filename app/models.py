from app import login_manager
from app.extensions import db
from datetime import datetime
import pytz
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

def get_beijing_time():
    """获取北京时间的辅助函数"""
    return datetime.now(pytz.timezone('Asia/Shanghai'))

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=get_beijing_time)

    # 关联任务
    tasks = db.relationship('Task', backref='owner', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    script_content = db.Column(db.Text, nullable=False)
    cron_expression = db.Column(db.String(100), nullable=False)

    schedule_type = db.Column(db.String(20), nullable=False, default='custom')
    schedule_config = db.Column(db.JSON)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=get_beijing_time)
    updated_at = db.Column(db.DateTime(timezone=True), default=get_beijing_time, onupdate=get_beijing_time)
    last_run = db.Column(db.DateTime(timezone=True))
    last_status = db.Column(db.String(50))
    timeout = db.Column(db.Integer, default=3600)
    max_retries = db.Column(db.Integer, default=0)
    retry_count = db.Column(db.Integer, default=0)

    script_source = db.Column(db.String(20), default='editor')
    original_filename = db.Column(db.String(255))

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    logs = db.relationship('TaskLog', backref='task', lazy='dynamic',
                          cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Task {self.name}>'

    @property
    def schedule_display(self):
        """返回人类可读的调度配置"""
        if not self.schedule_config:
            return self.cron_expression

        if self.schedule_type == 'once':
            # 确保时间显示为北京时间
            dt_str = self.schedule_config.get('datetime')
            try:
                dt = datetime.fromisoformat(dt_str)
                if dt.tzinfo is None:
                    dt = pytz.timezone('Asia/Shanghai').localize(dt)
                else:
                    dt = dt.astimezone(pytz.timezone('Asia/Shanghai'))
                return f"单次执行: {dt.strftime('%Y-%m-%d %H:%M:%S')}"
            except:
                return f"单次执行: {dt_str}"
        elif self.schedule_type == 'minutes':
            return f"每{self.schedule_config.get('value')}分钟"
        elif self.schedule_type == 'hourly':
            return f"每{self.schedule_config.get('value')}小时"
        elif self.schedule_type == 'daily':
            return f"每天 {self.schedule_config.get('time')}"
        elif self.schedule_type == 'weekly':
            weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            day = int(self.schedule_config.get('day', 0))
            return f"每周{weekdays[day]} {self.schedule_config.get('time')}"
        elif self.schedule_type == 'monthly':
            return f"每月{self.schedule_config.get('day')}日 {self.schedule_config.get('time')}"
        else:
            return self.cron_expression

    def update_schedule(self, schedule_type, config):
        """更新调度配置并生成对应的cron表达式"""
        self.schedule_type = schedule_type
        self.schedule_config = config

        if schedule_type == 'once':
            # 确保使用北京时间处理
            dt = datetime.fromisoformat(config['datetime'])
            if dt.tzinfo is None:
                dt = pytz.timezone('Asia/Shanghai').localize(dt)
            else:
                dt = dt.astimezone(pytz.timezone('Asia/Shanghai'))
            self.cron_expression = f"{dt.minute} {dt.hour} {dt.day} {dt.month} *"
        elif schedule_type == 'minutes':
            self.cron_expression = f"*/{config['value']} * * * *"
        elif schedule_type == 'hourly':
            self.cron_expression = f"0 */{config['value']} * * *"
        elif schedule_type == 'daily':
            hour, minute = config['time'].split(':')
            self.cron_expression = f"{minute} {hour} * * *"
        elif schedule_type == 'weekly':
            hour, minute = config['time'].split(':')
            self.cron_expression = f"{minute} {hour} * * {config['day']}"
        elif schedule_type == 'monthly':
            hour, minute = config['time'].split(':')
            self.cron_expression = f"{minute} {hour} {config['day']} * *"
        elif schedule_type == 'custom':
            self.cron_expression = config['expression']

class TaskLog(db.Model):
    __tablename__ = 'task_logs'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    start_time = db.Column(db.DateTime(timezone=True), nullable=False, default=get_beijing_time)
    end_time = db.Column(db.DateTime(timezone=True))
    status = db.Column(db.String(50))
    log_output = db.Column(db.Text)
    error_message = db.Column(db.Text)
    execution_time = db.Column(db.Float)

    def __repr__(self):
        return f'<TaskLog {self.task_id} {self.status}>'