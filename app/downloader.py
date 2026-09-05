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
    """解压 .Z (LZW) 文件，依次尝试 uncompress / gunzip / Python gzip"""
    import subprocess
    # 尝试 1: uncompress 命令
    try:
        proc = subprocess.run(
            ["uncompress", "-c"],
            input=data,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("uncompress 失败: %s", e)
    # 尝试 2: gunzip 命令（GNU gunzip 支持 .Z）
    try:
        proc = subprocess.run(
            ["gunzip", "-c"],
            input=data,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("gunzip 失败: %s", e)
    # 尝试 3: Python gzip（有些 .Z 实际是 gzip）
    try:
        return gzip.decompress(data)
    except Exception:
        pass
    # 无法解压，返回原始数据
    logger.warning("无法解压 .Z 文件，将保留原始数据")
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


def _is_html_content(data: bytes, content_type: str = "") -> bool:
    """检查内容是否为 HTML 页面（登录页、错误页等）"""
    if content_type and "html" in content_type.lower():
        return True
    # 检查前 512 字节是否以 HTML 标签开头
    head = data[:512].lstrip()
    if head[:1].lower() == b"<" and (b"html" in head[:20].lower() or b"<!doctype" in head[:20].lower()):
        return True
    return False


def download_http(url: str, username: Optional[str], password: Optional[str],
                  timeout: int = 60) -> tuple[bool, bytes, str]:
    """通过 HTTP/HTTPS 下载文件，自动拒绝 HTML 页面"""
    headers = {}
    auth = None
    if username and password:
        auth = (username, password)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(url, auth=auth, headers=headers)
            if resp.status_code != 200:
                return False, b"", f"HTTP {resp.status_code}"
            content_type = resp.headers.get("content-type", "")
            if _is_html_content(resp.content, content_type):
                return False, b"", "下载内容为 HTML 页面（可能需要登录或 URL 错误）"
            return True, resp.content, "OK"
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

    # 构建尝试的 URL 列表：原始 URL + .gz 后缀
    urls_to_try = [url]
    if not url.lower().endswith(".gz") and not url.lower().endswith(".z"):
        urls_to_try.append(url + ".gz")

    ok = False
    data = b""
    msg = ""
    used_url = url

    for try_url in urls_to_try:
        if source.protocol in ("http", "https"):
            ok, data, msg = download_http(try_url, source.username, source.password)
        elif source.protocol == "ftp":
            ok, data, msg = download_ftp(try_url, source.username, source.password)
        else:
            return False, None, f"不支持的协议: {source.protocol}"
        if ok:
            used_url = try_url
            break
        logger.warning("下载 %s 失败: %s", try_url, msg)

    if not ok:
        return False, None, msg

    # 根据实际下载的 URL 更新文件名和解压
    actual_filename = os.path.basename(urlparse(used_url).path)
    data = _decompress(data, actual_filename)

    # 如果是 .Z/.gz 解压后，调整扩展名
    if local_path.lower().endswith(".z"):
        local_path = local_path[:-2]
    elif local_path.lower().endswith(".gz"):
        local_path = local_path[:-3]

    with open(local_path, "wb") as f:
        f.write(data)

    size = len(data)
    logger.info("下载成功: %s (%d bytes)", local_path, size)
    return True, local_path, f"下载成功 ({size} bytes)"
