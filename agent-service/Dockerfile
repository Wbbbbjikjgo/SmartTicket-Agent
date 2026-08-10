# Agent 后端服务 Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 使用阿里云 PyPI 镜像安装依赖
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
    && pip config set global.trusted-host mirrors.aliyun.com

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令（可根据实际需求调整）
CMD ["python", "-c", "print('Agent Service Ready'); import time; time.sleep(999999)"]
