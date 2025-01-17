from pathlib import Path
from typing import Dict, Any
import json
import os


class Settings:
    def __init__(self):
        # 基础配置
        self.app_name: str = "Task Scheduler"
        self.base_dir: Path = Path(__file__).resolve().parent.parent.parent

        # 数据库配置
        self.database_url: str = "sqlite:///./scheduler.db"

        # 日志配置
        self.log_dir: Path = self.base_dir / "logs"

        # 脚本配置
        self.scripts_dir: Path = self.base_dir / "scripts"
        self.scripts: Dict[str, Any] = {
            "max_execution_time": 3600,  # 脚本最大执行时间（秒）
            "allowed_extensions": [".py"]
        }

        # 调度器配置
        self.scheduler: Dict[str, Any] = {
            "timezone": "UTC",
            "max_instances": 3,
            "misfire_grace_time": 3600
        }

        # 初始化必要的目录
        self._init_directories()

    def _init_directories(self):
        """初始化必要的目录"""
        directories = [
            self.log_dir,
            self.scripts_dir
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def validate_script_path(self, script_path: str) -> bool:
        """验证脚本路径"""
        full_path = self.scripts_dir / script_path
        return (
                full_path.suffix in self.scripts["allowed_extensions"] and
                full_path.is_file()
        )

    def get_script_files(self) -> list:
        """获取可用的脚本文件列表"""
        scripts = []
        for ext in self.scripts["allowed_extensions"]:
            scripts.extend(self.scripts_dir.glob(f"*{ext}"))
        return [script.name for script in scripts]


settings = Settings()