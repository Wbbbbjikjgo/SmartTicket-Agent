# Streamlit 前端 Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 使用阿里云 PyPI 镜像
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
    && pip config set global.trusted-host mirrors.aliyun.com

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

EXPOSE 8501

# 启动 Streamlit
CMD ["streamlit", "run", "web/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
