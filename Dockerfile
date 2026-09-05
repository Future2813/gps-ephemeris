# 使用 Alpine 基础镜像
FROM python:3.12-alpine AS builder

# 安装 RTKLIB 编译依赖
RUN apk add --no-cache \
    gcc \
    musl-dev \
    curl \
    tar \
    linux-headers

# 下载 RTKLIB 源码（使用 rtklibexplorer/RTKLIB 的 master 分支，支持 RINEX 4）
RUN for i in $(seq 1 10); do \
        echo "尝试下载 RTKLIB (第 $i 次)..." && \
        curl -L -f --retry 3 --retry-delay 5 --retry-all-errors \
             --connect-timeout 30 --max-time 300 \
             -o /tmp/rtklib.tar.gz \
             https://github.com/rtklibexplorer/RTKLIB/archive/refs/heads/master.tar.gz \
        && [ -s /tmp/rtklib.tar.gz ] && break || \
        { echo "下载失败，5秒后重试..."; sleep 5; }; \
    done && \
    ls -lh /tmp/rtklib.tar.gz && \
    file /tmp/rtklib.tar.gz   # 添加这行检查文件类型，便于调试

# 编译 RTKLIB（convbin + str2str）
RUN tar -xzf /tmp/rtklib.tar.gz -C /tmp \
    && mv /tmp/RTKLIB-master /tmp/rtklib \
    && cd /tmp/rtklib/src \
    && find . -name "*.c" -print0 | xargs -0 gcc -c -O2 -Wall -Wno-unused-but-set-variable -Wno-unused-variable -Wno-stringop-truncation -Wno-format-overflow \
         -DENAGLO -DENAGAL -DENAQZS -DENACMP -DENAIRN \
         -I. \
    && ar rcs librtk.a $(find . -name "*.o") \
    && CONVBIN_DIR=$(dirname $(find /tmp/rtklib -name convbin.c | head -1)) \
    && cd "$CONVBIN_DIR" \
    && gcc -O2 -Wall -I/tmp/rtklib/src -o convbin convbin.c -L/tmp/rtklib/src -lrtk -lm \
    && cp convbin /usr/local/bin/ \
    && STR2STR_DIR=$(dirname $(find /tmp/rtklib -name str2str.c | head -1)) \
    && cd "$STR2STR_DIR" \
    && gcc -O2 -Wall -I/tmp/rtklib/src -o str2str str2str.c -L/tmp/rtklib/src -lrtk -lm -lpthread \
    && cp str2str /usr/local/bin/ \
    && rm -rf /tmp/rtklib /tmp/rtklib.tar.gz

# 最终运行阶段
FROM python:3.12-alpine

# 安装运行时依赖
RUN apk add --no-cache \
    tzdata \
    curl \
    ca-certificates \
    libstdc++ \
    gzip

# 从 builder 阶段复制 RTKLIB 二进制
COPY --from=builder /usr/local/bin/convbin /usr/local/bin/convbin
COPY --from=builder /usr/local/bin/str2str /usr/local/bin/str2str

# 设置时区
ENV TZ=Asia/Shanghai

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/

# 创建数据目录
RUN mkdir -p /app/data/ephemeris /app/data/rtcm3 /app/data/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]