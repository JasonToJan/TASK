# app/scheduler.py
import logging

# 从 main.py 导入 scheduler 实例
from app.main import scheduler

# 可以在这里添加一些辅助函数
def get_scheduler():
    return scheduler

def shutdown_scheduler():
    try:
        scheduler.shutdown()
    except Exception as e:
        logging.error(f"Error shutting down scheduler: {e}")