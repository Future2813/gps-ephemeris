"""数据库模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text

from app.database import Base


class DataSource(Base):
    """星历数据源"""
    __tablename__ = "data_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    # 协议类型: http / https / ftp
    protocol = Column(String(10), nullable=False, default="https")
    # 基础 URL 模板，支持 {year} {doy} {yy} 占位符
    url_template = Column(String(500), nullable=False)
    # 用户名密码（可空，匿名访问时为空）
    username = Column(String(200), nullable=True)
    password = Column(String(200), nullable=True)
    # 是否启用
    enabled = Column(Boolean, default=True)
    # 优先级（数字越小优先级越高，多源时按顺序尝试）
    priority = Column(Integer, default=10)
    # 备注
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 最近一次下载状态
    last_status = Column(String(20), nullable=True)  # success / failed / none
    last_download_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)


class DownloadLog(Base):
    """下载日志"""
    __tablename__ = "download_logs"

    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)  # success / failed
    file_name = Column(String(200), nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class SystemStatus(Base):
    """系统状态（单条记录）"""
    __tablename__ = "system_status"

    id = Column(Integer, primary_key=True, default=1)
    last_download_time = Column(DateTime, nullable=True)
    last_convert_time = Column(DateTime, nullable=True)
    last_rtcm3_file = Column(String(200), nullable=True)
    last_rtcm3_size = Column(Integer, nullable=True)  # 字节
    scheduler_running = Column(Boolean, default=False)
