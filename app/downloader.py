"""星历下载器

支持从 IGS / BKG / 武汉 IGS 等数据源下载广播星历文件。
支持的协议: http / https / ftp
支持的文件: 原始 RINEX (.nav, .rnx, .YYn) 以及压缩 (.Z, .gz)
"""
import os
import io
import gzip
import logging
import ftplib
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger("ephemeris")


def build_date_params(dt: datetime) -> dict:
    """根据日期构建 URL 模板参数"""
    doy = dt.timetuple().tm_yday
    return {
        "year": dt.year,
        "yy": str(dt.year)[-2:],
        "doy": f"{doy:03d}",
        "doy0": f"{doy:03d}",
    }


def render_url(template: str, dt: datetime) -> str:
    """渲染 URL 模板，替换 {year} {yy} {doy} {doy0}"""
    params = build_date_params(dt)
    url = template
    for key, val in params.items():
        url = url.replace("{" + key + "}", str(val))
    return url


def _decompress_z(data: bytes) -> bytes:
    """解压 .Z (LZW) 文件，使用系统 uncompress 命令"""
    import subprocess
    try:
        proc = subprocess.run(
            ["uncompress", "-c"],
            input=data,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode == 0:
            return proc.stdout
    except Exception as e:
        logger.warning("uncompress 失败: %s", e)
    # 回退：尝试 gzip（有些 .Z 实际是 gzip）
    try:
        return gzip.decompress(data)
    except Exception:
        return data


def _decompress(data: bytes, filename: str) -> bytes:
    """根据扩展名解压"""
    name = filename.lower()
    if name.endswith(".z"):
        return _decompress_z(data)
    if name.endswith(".gz"):
        try:
            return gzip.decompress(data)
        except Exception:
            return data
    return data


def download_http(url: str, username: Optional[str], password: Optional[str],
                  timeout: int = 60) -> tuple[bool, bytes, str]:
    """通过 HTTP/HTTPS 下载文件"""
    headers = {}
    auth = None
    if username and password:
        auth = (username, password)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(url, auth=auth, headers=headers)
            if resp.status_code == 200:
                return True, resp.content, "OK"
            return False, b"", f"HTTP {resp.status_code}"
    except Exception as e:
        return False, b"", f"下载异常: {e}"


def download_ftp(url: str, username: Optional[str], password: Optional[str],
                 timeout: int = 60) -> tuple[bool, bytes, str]:
    """通过 FTP 下载文件"""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 21
    path = parsed.path
    user = username or "anonymous"
    passwd = password or "anonymous@"

    try:
        ftp = ftplib.FTP()
        ftp.connect(host, port, timeout=timeout)
        ftp.login(user, passwd)
        ftp.voidcmd("TYPE I")
        buf = io.BytesIO()
        ftp.retrbinary(f"RETR {path}", buf.write)
        ftp.quit()
        return True, buf.getvalue(), "OK"
    except Exception as e:
        return False, b"", f"FTP 异常: {e}"


def download_from_source(source, dt: datetime) -> tuple[bool, Optional[str], str]:
    """从单个数据源下载星历

    Returns:
        (是否成功, 保存的本地文件路径, 信息)
    """
    url = render_url(source.url_template, dt)
    filename = os.path.basename(urlparse(url).path)
    if not filename:
        filename = f"brdc_{dt.strftime('%Y%j')}.rnx"

    local_path = os.path.join(settings.ephemeris_dir, filename)

    logger.info("从 %s 下载: %s", source.name, url)

    if source.protocol in ("http", "https"):
        ok, data, msg = download_http(url, source.username, source.password)
    elif source.protocol == "ftp":
        ok, data, msg = download_ftp(url, source.username, source.password)
    else:
        return False, None, f"不支持的协议: {source.protocol}"

    if not ok:
        return False, None, msg

    # 解压
    data = _decompress(data, filename)

    # 如果是 .Z 解压后，调整扩展名
    if local_path.lower().endswith(".z"):
        local_path = local_path[:-2]

    with open(local_path, "wb") as f:
        f.write(data)

    size = len(data)
    logger.info("下载成功: %s (%d bytes)", local_path, size)
    return True, local_path, f"下载成功 ({size} bytes)"
