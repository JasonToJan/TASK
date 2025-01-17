import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config.config import settings

# 设置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(title=settings.app_name)

# 添加 CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确保静态文件目录存在
static_dir = "app/static"
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
    logger.info(f"Created static directory: {static_dir}")

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def read_index():
    index_path = "app/static/index.html"
    try:
        if os.path.exists(index_path):
            logger.debug(f"Serving index file from: {index_path}")
            return FileResponse(index_path)
        else:
            logger.error(f"Index file not found: {index_path}")
            raise HTTPException(status_code=404, detail="Index file not found")
    except Exception as e:
        logger.error(f"Error serving index file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))