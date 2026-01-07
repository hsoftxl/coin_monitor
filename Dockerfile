FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY src/ /app/src/
COPY .env.example /app/.env.example
COPY README.md /app/README.md

# 设置环境变量
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

# 无需健康检查，应用为后台服务

# 定义入口命令
CMD ["python", "src/main.py"]