# 使用 Alpine 基础镜像
FROM python:3.12-alpine AS builder

# 安装 RTKLIB 编译依赖
RUN apk add --no-cache \
    build-base \
    git \
    cmake \
    linux-headers

# 克隆并编译 RTKLIB（convbin + str2str 用于 RINEX -> RTCM3 转换）
# 手动编译：先编译核心库 librtk.a，再编译 convbin 和 str2str
RUN git clone --depth 1 -b rtklib_2.4.3 https://github.com/tomojitakasu/RTKLIB.git /tmp/rtklib \
    && cd /tmp/rtklib/src \
    && gcc -c -O2 -Wall -Wno-unused-but-set-variable -Wno-unused-variable \
         -DENAGLO -DENAGAL -DENAQZS -DENACMP -DENAIRN \
         -I. *.c \
    && ar rcs librtk.a *.o \
    && cd /tmp/rtklib/app/convbin \
    && gcc -O2 -Wall -I../../src -o convbin convbin.c -L../../src -lrtk -lm \
    && cp convbin /usr/local/bin/ \
    && cd /tmp/rtklib/app/str2str \
    && gcc -O2 -Wall -I../../src -o str2str str2str.c -L../../src -lrtk -lm -lpthread \
    && cp str2str /usr/local/bin/ \
    && rm -rf /tmp/rtklib

# 最终运行阶段
FROM python:3.12-alpine

# 安装运行时依赖
RUN apk add --no-cache \
    ncompress \
    tzdata \
    curl \
    ca-certificates \
    libstdc++

# 从 builder 阶段复制 RTKLIB 二进制
COPY --from=builder /usr/local/bin/convbin /usr/local/bin/convbin
COPY --from=builder /usr/local/bin/str2str /usr/local/bin/str2str

# 设置时区
ENV TZ=Asia/Shanghai

# 设置工作目录
WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/

# 创建数据目录
RUN mkdir -p /app/data/ephemeris /app/data/rtcm3 /app/data/logs

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
