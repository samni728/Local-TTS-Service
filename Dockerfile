# 使用官方的、轻量的 Python 3.10 镜像作为基础
FROM python:3.10-slim

# 设置容器内的工作目录
WORKDIR /app

# 将 requirements.txt 复制到工作目录
COPY requirements.txt .

# 安装项目依赖，--no-cache-dir 参数可以减小镜像体积
RUN pip install --no-cache-dir -r requirements.txt

# 将项目的所有文件复制到工作目录
COPY . .

# 声明容器将要监听的端口（这个端口与 config.json 中的端口对应）
# 实际的端口映射将在 docker-compose.yml 中完成
EXPOSE 5050

# 容器启动时要执行的命令
CMD ["python", "app.py"]