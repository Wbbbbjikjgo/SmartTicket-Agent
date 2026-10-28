# Agent 后端服务 Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 使用阿里云 PyPI 镜像安装依赖
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
    && pip config set global.trusted-host mirrors.aliyun.com

# Debian 源换阿里云镜像
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir --default-timeout=300 -r requirements.txt

# 复制项目代码
COPY . .

# 启动 Kafka 后台消费者（部门工单确认 + 解决事件沉淀）
CMD ["python", "data/ingestion/kafka_queue.py"]
