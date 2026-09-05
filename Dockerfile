# 使用 Alpine 基础镜像
FROM python:3.12-alpine AS builder

# 安装 RTKLIB 编译依赖
RUN apk add --no-cache \
    gcc \
    musl-dev \
    tar \
    linux-headers

# 复制本地下载好的源码包（不再使用 curl 下载）
COPY rtklib-master.tar.gz /tmp/rtklib.tar.gz

# 验证文件是否为 gzip（可选）
RUN file /tmp/rtklib.tar.gz

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

COPY --from=builder /usr/local/bin/convbin /usr/local/bin/convbin
COPY --from=builder /usr/local/bin/str2str /usr/local/bin/str2str

ENV TZ=Asia/Shanghai
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
RUN mkdir -p /app/data/ephemeris /app/data/rtcm3 /app/data/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]