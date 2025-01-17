from apscheduler.schedulers.background import BackgroundScheduler
from app.config.config import settings
import logging

# 创建调度器
scheduler = BackgroundScheduler(
    timezone=settings.scheduler['timezone'],
    max_instances=settings.scheduler['max_instances']
)

def init_scheduler():
    try:
        scheduler.start()
        logging.info("Scheduler started successfully")
    except Exception as e:
        logging.error(f"Error starting scheduler: {str(e)}")
        raise

def shutdown_scheduler():
    try:
        scheduler.shutdown()
        logging.info("Scheduler shutdown successfully")
    except Exception as e:
        logging.error(f"Error shutting down scheduler: {str(e)}")