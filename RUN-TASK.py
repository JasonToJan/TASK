import os
import sys
import time

import pytz
from datetime import datetime
from app import create_app, db

# 打印当前的 Python 路径
print("Python path:", sys.path)

# 设置默认时区为北京时间
os.environ['TZ'] = 'Asia/Shanghai'
if hasattr(time, 'tzset'):
    time.tzset()


def configure_timezone(app):
    """配置应用的时区设置"""
    # 设置Flask应用的默认时区
    app.config['TIMEZONE'] = 'Asia/Shanghai'

    # 设置Jinja2模板的全局变量
    app.jinja_env.globals.update(
        timezone=pytz.timezone,
        now=datetime.now
    )

    # 确保APScheduler使用正确的时区
    app.config['SCHEDULER_TIMEZONE'] = 'Asia/Shanghai'


# 创建应用实例
app = create_app('development')

# 配置时区
configure_timezone(app)

# 验证配置是否正确加载
print("App config:", app.config)
print(f"Current timezone: {datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Z %z')}")


@app.route('/')
def index():
    return 'Hello, Flask!'


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8892, debug=True)