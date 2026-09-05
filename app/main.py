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
    """初始化内置数据源：IGS、BKG、武汉 IGS"""
    db = SessionLocal()
    try:
        defaults = [
            {
                "name": "IGS (CDDIS)",
                "protocol": "https",
                "url_template": "https://cddis.nasa.gov/archive/gnss/data/daily/{year}/{doy}/{yy}n/BRDC00IGS_R_{year}{doy}0000_01D_MN.rnx",
                "username": "",
                "password": "",
                "enabled": True,
                "priority": 1,
                "remark": "NASA CDDIS 全球 IGS 合并广播星历（多系统）。需要 Earthdata 账号，在上方填写用户名密码",
            },
            {
                "name": "BKG",
                "protocol": "https",
                "url_template": "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/{year}/{doy}/BRDC00IGS_R_{year}{doy}0000_01D_MN.rnx",
                "username": "",
                "password": "",
                "enabled": True,
                "priority": 2,
                "remark": "德国 BKG 提供的 IGS 广播星历，通常无需登录",
            },
            {
                "name": "武汉 IGS (CDIS)",
                "protocol": "ftp",
                "url_template": "ftp://igs.gnsswhu.cn/pub/gnss/data/daily/{year}/{doy}/{yy}n/BRDC00WUH_R_{year}{doy}0000_01D_MN.rnx",
                "username": "anonymous",
                "password": "anonymous@",
                "enabled": True,
                "priority": 3,
                "remark": "武汉大学 IGS 数据中心广播星历，匿名 FTP 访问",
            },
        ]
        for ds in defaults:
            exists = db.query(DataSource).filter(DataSource.name == ds["name"]).first()
            if not exists:
                db.add(DataSource(**ds))
                logger.info("已添加内置数据源: %s", ds["name"])
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
