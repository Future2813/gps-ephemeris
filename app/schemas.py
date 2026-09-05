"""Pydantic 数据模型"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DataSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    protocol: str = Field(default="https", pattern="^(http|https|ftp)$")
    url_template: str = Field(..., min_length=1)
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: bool = True
    priority: int = 10
    remark: Optional[str] = None


class DataSourceUpdate(BaseModel):
    protocol: Optional[str] = None
    url_template: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    remark: Optional[str] = None


class DataSourceOut(BaseModel):
    id: int
    name: str
    protocol: str
    url_template: str
    username: Optional[str] = None
    # 密码不返回
    enabled: bool
    priority: int
    remark: Optional[str] = None
    last_status: Optional[str] = None
    last_download_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class StatusOut(BaseModel):
    last_download_time: Optional[datetime] = None
    last_convert_time: Optional[datetime] = None
    last_rtcm3_file: Optional[str] = None
    last_rtcm3_size: Optional[int] = None
    scheduler_running: bool = False
