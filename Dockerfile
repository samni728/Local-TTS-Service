# 使用官方的、轻量的 Python 3.10 镜像作为基础
FROM python:3.10-slim

# --- 优化核心：允许在构建时动态指定 PyPI 镜像 ---
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

# --- 安装核心系统依赖：ffmpeg ---
RUN apt-get update && apt-get install -y ffmpeg --no-install-recommends && rm -rf /var/lib/apt/lists/*

# 设置容器内的工作目录
WORKDIR /app

# 将 requirements.txt 复制到工作目录
COPY requirements.txt .

# 使用环境变量安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i ${PIP_INDEX_URL}

# 将项目的所有文件复制到工作目录
COPY . .

# 声明容器将要监听的端口
EXPOSE 5050

# 容器启动时要执行的命令
CMD ["python", "app.py"]