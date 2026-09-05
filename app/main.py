"""FastAPI 应用入口"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import init_db, SessionLocal
from app.models import DataSource, SystemStatus
from app.scheduler import run_download_pipeline
from app.api import router as api_router

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ephemeris")

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def seed_default_sources():
    """初始化内置数据源：BKG、武汉 IGS、IGS (CDDIS)
    优先级：免认证的 BKG 和武汉 IGS 优先，需要账号的 CDDIS 最后
    """
    db = SessionLocal()
    try:
        defaults = [
            {
                "name": "武汉 IGS",
                "protocol": "ftp",
                "url_template": "ftp://igs.gnsswhu.cn/pub/gps/data/daily/{year}/brdc/BRD400DLR_S_{year}{doy}0000_01D_MN.rnx.gz",
                "username": "anonymous",
                "password": "anonymous@",
                "enabled": True,
                "priority": 1,
                "remark": "武汉大学 IGS 数据中心，国内最快，RINEX4 多系统广播星历",
            },
            {
                "name": "IGN (法国)",
                "protocol": "ftp",
                "url_template": "ftp://igs.ign.fr/pub/igs/data/{year}/{doy}/BRDC00IGN_R_{year}{doy}0000_01D_MN.rnx.gz",
                "username": "anonymous",
                "password": "anonymous@",
                "enabled": True,
                "priority": 2,
                "remark": "法国 IGN 地理信息局，匿名 FTP，多系统广播星历",
            },
            {
                "name": "BKG",
                "protocol": "https",
                "url_template": "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/{year}/{doy}/BRDM00DLR_S_{year}{doy}0000_01D_MN.rnx.gz",
                "username": "",
                "password": "",
                "enabled": True,
                "priority": 3,
                "remark": "德国 BKG 提供的 DLR 多系统广播星历，HTTP 协议，无需登录",
            },
        ]
        for ds in defaults:
            existing = db.query(DataSource).filter(DataSource.name == ds["name"]).first()
            if not existing:
                db.add(DataSource(**ds))
                logger.info("已添加内置数据源: %s", ds["name"])
            else:
                # 更新内置数据源的 URL 和优先级（保留用户的账号密码设置）
                existing.url_template = ds["url_template"]
                existing.protocol = ds["protocol"]
                existing.priority = ds["priority"]
                existing.remark = ds["remark"]
                existing.enabled = ds["enabled"]
                logger.info("已更新内置数据源: %s", ds["name"])
        # 删除已废弃的内置数据源
        deprecated_names = ["IGS (CDDIS)", "武汉 IGS (CDIS)"]
        for name in deprecated_names:
            old = db.query(DataSource).filter(DataSource.name == name).first()
            if old:
                db.delete(old)
                logger.info("已删除废弃数据源: %s", name)
        # 确保系统状态记录存在
        if not db.query(SystemStatus).first():
            db.add(SystemStatus(id=1))
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    init_db()
    seed_default_sources()

    # 启动定时调度器
    scheduler.add_job(
        run_download_pipeline,
        "interval",
        minutes=settings.download_interval_minutes,
        id="ephemeris_download",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("调度器已启动，每 %d 分钟下载一次", settings.download_interval_minutes)

    # 启动后立即执行一次下载
    try:
        result = run_download_pipeline()
        logger.info("启动首次下载结果: %s", result)
    except Exception as e:
        logger.error("启动首次下载异常: %s", e)

    yield

    # 关闭时
    scheduler.shutdown(wait=False)
    logger.info("调度器已停止")


app = FastAPI(title="GPS 广播星历下载服务", version="1.0.0", lifespan=lifespan)

# 注册 API 路由
app.include_router(api_router)

# 静态文件（网页管理界面）
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(static_dir, "index.html"))
