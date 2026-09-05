# 改用 Debian slim 基础镜像（兼容 glibc，以便运行 gfzrnx）
FROM python:3.12-slim AS builder

# 安装编译依赖（Debian 包管理）
RUN apt-get update && apt-get install -y \
    gcc \
    make \
    wget \
    tar \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# 下载 RTKLIB 源码包（官方 2.4.3）
RUN wget -q --tries=5 --timeout=30 \
    https://github.com/tomojitakasu/RTKLIB/archive/refs/tags/2.4.3.tar.gz \
    -O /tmp/rtklib.tar.gz

# 编译 RTKLIB（解压后目录名为 RTKLIB-2.4.3）
RUN tar -xzf /tmp/rtklib.tar.gz -C /tmp \
    && mv /tmp/RTKLIB-2.4.3 /tmp/rtklib \
    && cd /tmp/rtklib/src \
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

# 下载 gfzrnx（约 2MB，glibc 静态编译）
RUN wget -q --tries=5 --timeout=30 \
    https://download.gfz-potsdam.de/gnss/products/GFZRNX/GFZRNX_linux_64bit.tar.gz \
    -O /tmp/gfzrnx.tar.gz \
    && tar -xzf /tmp/gfzrnx.tar.gz -C /tmp \
    && cp /tmp/gfzrnx /usr/local/bin/ \
    && chmod +x /usr/local/bin/gfzrnx \
    && rm -rf /tmp/gfzrnx.tar.gz /tmp/gfzrnx

# 最终运行阶段
FROM python:3.12-slim

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

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
RUN mkdir -p /app/data/ephemeris /app/data/rtcm3 /app/data/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]