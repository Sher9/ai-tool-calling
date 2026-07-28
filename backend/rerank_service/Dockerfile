FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV HF_HOME=/data/models
VOLUME ["/data/models"]

EXPOSE 8089
CMD ["uvicorn", "rerank_service.main:app", "--host", "0.0.0.0", "--port", "8089"]
