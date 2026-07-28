FROM python:3.11-slim

WORKDIR /app

# 仅安装 embedding 服务依赖，保持镜像精简
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 模型权重持久化，避免容器重建后重复下载
ENV HF_HOME=/data/models
VOLUME ["/data/models"]

EXPOSE 8088
CMD ["uvicorn", "embedding_service.main:app", "--host", "0.0.0.0", "--port", "8088"]
