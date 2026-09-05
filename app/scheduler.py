"""调度器：定时下载星历并转换为 RTCM3"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import DataSource, DownloadLog, SystemStatus
from app.downloader import download_from_source
from app.converter import convert_rinex_to_rtcm3

logger = logging.getLogger("ephemeris")


def _log_download(db: Session, source_name: str, status: str, file_name: Optional[str], message: str):
    log = DownloadLog(
        source_name=source_name,
        status=status,
        file_name=file_name,
        message=message,
    )
    db.add(log)
    db.commit()


def run_download_pipeline() -> dict:
    """执行一次完整的下载+转换流程

    Returns:
        结果字典
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # 获取所有启用的数据源，按优先级排序
        sources = (
            db.query(DataSource)
            .filter(DataSource.enabled.is_(True))
            .order_by(DataSource.priority.asc())
            .all()
        )

        if not sources:
            logger.warning("没有启用的数据源")
            return {"success": False, "message": "没有启用的数据源"}

        # 按优先级依次尝试，直到成功
        rinex_path: Optional[str] = None
        used_source: Optional[DataSource] = None

        for source in sources:
            ok, path, msg = download_from_source(source, now)
            if ok and path:
                rinex_path = path
                used_source = source
                source.last_status = "success"
                source.last_download_at = datetime.utcnow()
                source.last_error = None
                db.commit()
                _log_download(db, source.name, "success", os.path.basename(path), msg)
                break
            else:
                source.last_status = "failed"
                source.last_download_at = datetime.utcnow()
                source.last_error = msg
                db.commit()
                _log_download(db, source.name, "failed", None, msg)
                logger.warning("数据源 %s 下载失败: %s", source.name, msg)

        if not rinex_path or not used_source:
            return {"success": False, "message": "所有数据源均下载失败"}

        # 转换为 RTCM3
        rtcm3_path = os.path.join(settings.rtcm3_dir, settings.rtcm3_output_name)
        ok, msg = convert_rinex_to_rtcm3(rinex_path, rtcm3_path)

        # 更新系统状态
        status = db.query(SystemStatus).first()
        if not status:
            status = SystemStatus(id=1)
            db.add(status)
        status.last_download_time = datetime.utcnow()
        if ok:
            status.last_convert_time = datetime.utcnow()
            status.last_rtcm3_file = settings.rtcm3_output_name
            status.last_rtcm3_size = os.path.getsize(rtcm3_path) if os.path.exists(rtcm3_path) else None
        db.commit()

        if not ok:
            logger.error("RTCM3 转换失败: %s", msg)
            return {"success": False, "message": f"下载成功但转换失败: {msg}",
                    "source": used_source.name}

        size = os.path.getsize(rtcm3_path)
        logger.info("流程完成: 数据源=%s, RTCM3=%s (%d bytes)", used_source.name, rtcm3_path, size)
        return {
            "success": True,
            "source": used_source.name,
            "rinex_file": os.path.basename(rinex_path),
            "rtcm3_file": settings.rtcm3_output_name,
            "rtcm3_size": size,
        }

    except Exception as e:
        logger.exception("下载流程异常: %s", e)
        return {"success": False, "message": f"流程异常: {e}"}
    finally:
        db.close()
