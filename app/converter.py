"""RINEX 导航文件 -> RTCM3 转换器

使用 RTKLIB 的 convbin / str2str 将广播星历 RINEX 文件转换为 RTCM3 格式。
RTCM3 中包含四大系统星历消息：
  GPS: 1019, GLONASS: 1020, Galileo: 1041/1042, BeiDou: 1044/1045
"""
import os
import subprocess
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger("ephemeris")


def _run_cmd(cmd: list[str], timeout: int = 120) -> tuple[bool, str]:
    """运行外部命令，返回 (是否成功, 输出信息)"""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            logger.error("命令失败 %s: %s", " ".join(cmd), output)
            return False, output
        return True, output
    except subprocess.TimeoutExpired:
        return False, "命令执行超时"
    except FileNotFoundError:
        return False, f"命令未找到: {cmd[0]}"
    except Exception as e:
        return False, f"执行异常: {e}"


def _find_rtklib_tool(name: str) -> Optional[str]:
    """查找 RTKLIB 工具路径"""
    for path in [f"/usr/local/bin/{name}", f"/usr/bin/{name}", name]:
        if os.path.exists(path) or path == name:
            return path
    return None


def _is_valid_rinex(filepath: str) -> bool:
    """检查文件是否为有效的 RINEX 格式（头部包含 RINEX VERSION）"""
    try:
        with open(filepath, "rb") as f:
            head = f.read(200)
        # RINEX 文件头部应包含 "RINEX VERSION"
        return b"RINEX VERSION" in head
    except Exception:
        return False


def convert_rinex_to_rtcm3(rinex_path: str, output_path: str) -> tuple[bool, str]:
    """将 RINEX 导航文件转换为 RTCM3

    Args:
        rinex_path: 输入的 RINEX 导航文件路径（.nav / .rnx / .YYn）
        output_path: 输出 RTCM3 文件路径

    Returns:
        (是否成功, 信息)
    """
    if not os.path.exists(rinex_path):
        return False, f"输入文件不存在: {rinex_path}"

    # 检查文件是否为空
    if os.path.getsize(rinex_path) == 0:
        return False, f"输入文件为空: {rinex_path}"

    # 检查是否为有效 RINEX 文件
    if not _is_valid_rinex(rinex_path):
        # 读取前 200 字节用于诊断
        try:
            with open(rinex_path, "rb") as f:
                head = f.read(200)
            preview = head[:100].decode("utf-8", errors="replace")
        except Exception:
            preview = "<无法读取>"
        return False, f"文件不是有效的 RINEX 格式。前100字节: {preview}"

    convbin = _find_rtklib_tool("convbin")
    str2str = _find_rtklib_tool("str2str")

    # 优先使用 convbin（对广播星历导航文件支持更好）
    if convbin:
        if os.path.exists(output_path):
            os.remove(output_path)
        ok, msg = _run_cmd([
            convbin,
            "-r", "rinex",
            "-o", output_path,
            rinex_path,
        ], timeout=180)
        if ok and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info("convbin 转换成功: %s -> %s", rinex_path, output_path)
            return True, "convbin 转换成功"
        last_msg = msg

    # 回退到 str2str
    if str2str:
        if os.path.exists(output_path):
            os.remove(output_path)
        ok, msg = _run_cmd([
            str2str,
            "-in", f"{rinex_path}#rinex",
            "-out", f"{output_path}#rtcm3",
        ], timeout=180)
        if ok and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info("str2str 转换成功: %s -> %s", rinex_path, output_path)
            return True, "str2str 转换成功"
        last_msg = msg

    # 两个工具都没有
    if not convbin and not str2str:
        return False, "未找到 convbin 或 str2str，请确认 RTKLIB 已正确安装"

    return False, f"转换失败: {last_msg}"
