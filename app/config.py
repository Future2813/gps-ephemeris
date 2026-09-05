"""应用配置"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 管理员账户
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin123")
    secret_key: str = os.getenv("SECRET_KEY", "ephemeris-secret-key-change-me")

    # 数据目录
    data_dir: str = "/app/data"
    ephemeris_dir: str = "/app/data/ephemeris"
    rtcm3_dir: str = "/app/data/rtcm3"
    log_dir: str = "/app/data/logs"
    db_path: str = "/app/db/ephemeris.db"

    # 调度
    download_interval_minutes: int = 60  # 每小时下载一次

    # RTCM3 输出
    rtcm3_output_name: str = "latest.rtcm3"

    class Config:
        env_file = ".env"


settings = Settings()

# 确保目录存在
for d in [settings.data_dir, settings.ephemeris_dir, settings.rtcm3_dir,
          settings.log_dir, os.path.dirname(settings.db_path)]:
    os.makedirs(d, exist_ok=True)
