# 使用清华源加速 apt 安装
FROM python:3.12-slim AS builder

# 替换为国内镜像源（清华源）
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 安装编译依赖（包含解压 gfzrnx 可能需要的工具）
RUN apt-get update && apt-get install -y \
    gcc \
    make \
    tar \
    libc6-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ---------- RTKLIB ----------
# 复制您本地的 RTKLIB 源码包（Debian 格式）
COPY rtklib_2.4.3+dfsg1.orig.tar.gz /tmp/rtklib.tar.gz

# 解压并重命名目录（适应任何以 rtklib- 开头的目录名）
RUN tar -xzf /tmp/rtklib.tar.gz -C /tmp \
    && mv /tmp/rtklib-* /tmp/rtklib

# 编译 RTKLIB
RUN cd /tmp/rtklib/src \
    && gcc -c -O2 -Wall -Wno-unused-but-set-variable -Wno-unused-variable -Wno-stringop-truncation -Wno-format-overflow \
         -DENAGLO -DENAGAL -DENAQZS -DENACMP -DENAIRN \
         -I. $(find . -name "*.c") \
    && ar rcs librtk.a *.o \
    && cd /tmp/rtklib/app/convbin \
    && gcc -O2 -Wall -I/tmp/rtklib/src -o convbin convbin.c -L/tmp/rtklib/src -lrtk -lm \
    && cp convbin /usr/local/bin/ \
    && cd /tmp/rtklib/app/str2str \
    && gcc -O2 -Wall -I/tmp/rtklib/src -o str2str str2str.c -L/tmp/rtklib/src -lrtk -lm -lpthread \
    && cp str2str /usr/local/bin/ \
    && rm -rf /tmp/rtklib /tmp/rtklib.tar.gz

# ---------- gfzrnx ----------
# 复制您本地的 gfzrnx 可执行文件（已重命名为 gfzrnx）
COPY gfzrnx /tmp/gfzrnx
RUN cp /tmp/gfzrnx /usr/local/bin/ \
    && chmod +x /usr/local/bin/gfzrnx \
    && rm -rf /tmp/gfzrnx

# ---------- 最终运行阶段 ----------
FROM python:3.12-slim

# 使用清华源加速
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    tzdata \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai
WORKDIR /app

# 复制编译好的二进制
COPY --from=builder /usr/local/bin/convbin /usr/local/bin/convbin
COPY --from=builder /usr/local/bin/str2str /usr/local/bin/str2str
COPY --from=builder /usr/local/bin/gfzrnx /usr/local/bin/gfzrnx

# 安装 Python 依赖（使用清华 PyPI 镜像）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY app/ ./app/
RUN mkdir -p /app/data/ephemeris /app/data/rtcm3 /app/data/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]