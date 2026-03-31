FROM python:3.11-slim

WORKDIR /app

# 安装 git（用于 clone YARS）
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 下载 YARS 爬虫库
RUN git clone https://github.com/datavorous/YARS.git /app/YARS --depth 1

# 复制源码
COPY src/api_server.py .
COPY src/scraper.py .

# 启动服务
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]