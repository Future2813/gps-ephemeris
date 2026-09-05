"""API 路由"""
import os
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import DataSource, DownloadLog, SystemStatus
from app.schemas import (
    DataSourceCreate, DataSourceUpdate, DataSourceOut,
    LoginRequest, StatusOut,
)
from app.config import settings
from app.auth import (
    create_session_token, verify_session_token, get_current_user,
    SESSION_COOKIE,
)
from app.scheduler import run_download_pipeline

logger = logging.getLogger("ephemeris")
router = APIRouter(prefix="/api")


# ---------- 认证 ----------
@router.post("/login")
def login(req: LoginRequest, response: Response):
    if req.username == settings.admin_username and req.password == settings.admin_password:
        token = create_session_token(req.username)
        response.set_cookie(
            SESSION_COOKIE, token,
            httponly=True, samesite="lax", max_age=7 * 24 * 3600,
        )
        return {"success": True, "username": req.username}
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"success": True}


@router.get("/me")
def me(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    username = verify_session_token(token) if token else None
    return {"authenticated": bool(username), "username": username}


# ---------- 健康检查（无需登录） ----------
@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ---------- 数据源管理 ----------
@router.get("/sources", response_model=list[DataSourceOut])
def list_sources(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    sources = db.query(DataSource).order_by(DataSource.priority.asc()).all()
    return sources


@router.post("/sources", response_model=DataSourceOut)
def create_source(data: DataSourceCreate, db: Session = Depends(get_db),
                  _: str = Depends(get_current_user)):
    if db.query(DataSource).filter(DataSource.name == data.name).first():
        raise HTTPException(status_code=400, detail="数据源名称已存在")
    source = DataSource(**data.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.put("/sources/{source_id}", response_model=DataSourceOut)
def update_source(source_id: int, data: DataSourceUpdate, db: Session = Depends(get_db),
                  _: str = Depends(get_current_user)):
    source = db.query(DataSource).get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="数据源不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(source, key, val)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db),
                  _: str = Depends(get_current_user)):
    source = db.query(DataSource).get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="数据源不存在")
    db.delete(source)
    db.commit()
    return {"success": True}


# ---------- 系统状态 ----------
@router.get("/status", response_model=StatusOut)
def get_status(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    s = db.query(SystemStatus).first()
    if not s:
        return StatusOut()
    return StatusOut(
        last_download_time=s.last_download_time,
        last_convert_time=s.last_convert_time,
        last_rtcm3_file=s.last_rtcm3_file,
        last_rtcm3_size=s.last_rtcm3_size,
        scheduler_running=s.scheduler_running,
    )


# ---------- 下载日志 ----------
@router.get("/logs")
def get_logs(limit: int = 50, db: Session = Depends(get_db),
             _: str = Depends(get_current_user)):
    logs = (
        db.query(DownloadLog)
        .order_by(DownloadLog.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": l.id,
            "source_name": l.source_name,
            "status": l.status,
            "file_name": l.file_name,
            "message": l.message,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


# ---------- 手动触发下载 ----------
@router.post("/download/trigger")
def trigger_download(_: str = Depends(get_current_user)):
    result = run_download_pipeline()
    return result


# ---------- RTCM3 文件下载（供终端设备获取星历） ----------
@router.get("/rtcm3/latest")
def get_latest_rtcm3():
    """终端设备通过此接口获取最新 RTCM3 星历文件（无需登录）"""
    rtcm3_path = os.path.join(settings.rtcm3_dir, settings.rtcm3_output_name)
    if not os.path.exists(rtcm3_path):
        raise HTTPException(status_code=404, detail="RTCM3 文件尚未生成，请等待下载任务完成")
    return FileResponse(
        rtcm3_path,
        media_type="application/octet-stream",
        filename=settings.rtcm3_output_name,
    )


@router.get("/rtcm3/info")
def get_rtcm3_info():
    """获取 RTCM3 文件信息（无需登录）"""
    rtcm3_path = os.path.join(settings.rtcm3_dir, settings.rtcm3_output_name)
    if not os.path.exists(rtcm3_path):
        return {"available": False}
    stat = os.stat(rtcm3_path)
    return {
        "available": True,
        "filename": settings.rtcm3_output_name,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }
