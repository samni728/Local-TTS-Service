# 使用官方的、轻量的 Python 3.10 镜像作为基础
FROM python:3.10-slim

# --- 优化核心：允许在构建时动态指定 PyPI 镜像 ---
# 1. 定义一个构建时参数 PIP_INDEX_URL，并设置一个默认值（官方源）
ARG PIP_INDEX_URL=https://pypi.org/simple

# 2. 将这个参数的值设置成一个环境变量，以便后续命令可以使用
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

# 设置容器内的工作目录
WORKDIR /app

# 将 requirements.txt 复制到工作目录
COPY requirements.txt .

# 3. 在 pip install 命令中使用这个环境变量
#    如果构建时没有提供 PIP_INDEX_URL，它会使用默认的官方源
#    如果提供了，它会使用指定的镜像源
RUN pip install --no-cache-dir -r requirements.txt -i ${PIP_INDEX_URL}

# 将项目的所有文件复制到工作目录
COPY . .

# 声明容器将要监听的端口
EXPOSE 5050

# 容器启动时要执行的命令
CMD ["python", "app.py"]