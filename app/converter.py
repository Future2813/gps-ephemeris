"""RINEX 导航文件 -> RTCM3 转换器

使用 RTKLIB 的 convbin / str2str 将广播星历 RINEX 文件转换为 RTCM3 格式。
若输入为 RINEX 4，先用 gfzrnx 降级为 RINEX 3 再转换。
"""
import os
import subprocess
import logging
import tempfile
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


def _find_tool(name: str) -> Optional[str]:
    """通用查找可执行文件"""
    for path in [f"/usr/local/bin/{name}", f"/usr/bin/{name}", name]:
        if os.path.exists(path) or path == name:
            return path
    return None


def _find_rtklib_tool(name: str) -> Optional[str]:
    """查找 RTKLIB 工具（兼容旧名）"""
    return _find_tool(name)


def _is_valid_rinex(filepath: str) -> bool:
    """检查文件是否为有效的 RINEX 格式（头部包含 RINEX VERSION）"""
    try:
        with open(filepath, "rb") as f:
            head = f.read(200)
        return b"RINEX VERSION" in head
    except Exception:
        return False


def _get_rinex_version(filepath: str) -> Optional[float]:
    """读取 RINEX 文件头部版本号，返回浮点数如 4.02 或 3.05"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "RINEX VERSION" in line:
                    parts = line.split()
                    if parts:
                        return float(parts[0])
    except Exception:
        pass
    return None


def _downgrade_rinex4_with_gfzrnx(input_path: str, output_path: str) -> tuple[bool, str]:
    """使用 gfzrnx 将 RINEX 4 文件降级为 RINEX 3.x"""
    gfzrnx = _find_tool("gfzrnx")
    if not gfzrnx:
        return False, "未找到 gfzrnx，无法降级 RINEX 4 文件"
    cmd = [gfzrnx, "-fin", input_path, "-fout", output_path, "-vo", "3"]
    return _run_cmd(cmd, timeout=180)


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

    if os.path.getsize(rinex_path) == 0:
        return False, f"输入文件为空: {rinex_path}"

    if not _is_valid_rinex(rinex_path):
        try:
            with open(rinex_path, "rb") as f:
                head = f.read(200)
            preview = head[:100].decode("utf-8", errors="replace")
        except Exception:
            preview = "<无法读取>"
        return False, f"文件不是有效的 RINEX 格式。前100字节: {preview}"

    # 检测版本，若为 4.x 则降级
    version = _get_rinex_version(rinex_path)
    final_input = rinex_path
    temp_file = None
    if version is not None and version >= 4.0:
        logger.info("检测到 RINEX %s，尝试降级到 RINEX 3", version)
        temp_fd, temp_file = tempfile.mkstemp(suffix=".rnx", prefix="v3_")
        os.close(temp_fd)
        ok, msg = _downgrade_rinex4_with_gfzrnx(rinex_path, temp_file)
        if not ok:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            return False, f"RINEX 4 降级失败: {msg}"
        final_input = temp_file
        logger.info("降级成功: %s -> %s", rinex_path, temp_file)

    # 调用 convbin / str2str 转换
    convbin = _find_rtklib_tool("convbin")
    str2str = _find_rtklib_tool("str2str")
    last_msg = "未找到可用的转换工具"

    if convbin:
        if os.path.exists(output_path):
            os.remove(output_path)
        ok, msg = _run_cmd([
            convbin,
            "-r", "0",
            "-o", output_path,
            final_input,
        ], timeout=180)
        if ok and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info("convbin 转换成功: %s -> %s", final_input, output_path)
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            return True, "convbin 转换成功"
        last_msg = msg

    if str2str:
        if os.path.exists(output_path):
            os.remove(output_path)
        ok, msg = _run_cmd([
            str2str,
            "-in", f"{final_input}#rinex",
            "-out", f"{output_path}#rtcm3",
        ], timeout=180)
        if ok and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info("str2str 转换成功: %s -> %s", final_input, output_path)
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            return True, "str2str 转换成功"
        last_msg = msg

    if not convbin and not str2str:
        return False, "未找到 convbin 或 str2str，请确认 RTKLIB 已正确安装"

    if temp_file and os.path.exists(temp_file):
        os.remove(temp_file)
    return False, f"转换失败: {last_msg}"