# Demand Radar - Reddit Scraper API

从 Reddit 抓取用户痛点数据，生成 `DemandReport` 格式的需求分析报告。

## 功能

- 🔍 关键词搜索 Reddit 帖子
- 💬 抓取帖子 + 评论内容
- 📊 自动提取痛点 (pain points)
- 📈 计算机会指标 (demand / competition / monetization)
- 🚀 FastAPI 服务，支持 Vercel 前端调用

## 快速开始

### 1. 安装

```bash
git clone https://github.com/bellefly-god/demand-radar-reddit.git
cd demand-radar-reddit/src
chmod +x install.sh
./install.sh
```

安装脚本会：
- 检查 Python 环境
- 安装依赖 (fastapi, uvicorn, requests, Pygments)
- 下载 YARS 爬虫库
- 创建虚拟环境

### 2. 启动服务

```bash
cd src
source venv/bin/activate  # 使用虚拟环境
python api_server.py
```

服务运行在 `http://localhost:8000`

### 3. 测试接口

```bash
# 完整报告
curl "http://localhost:8000/scrape?keyword=startup+pain+points"

# 只返回 quotes
curl "http://localhost:8000/quotes?keyword=meal+prep"

# 只返回痛点
curl "http://localhost:8000/pain-points?keyword=fitness+app"

# 健康检查
curl "http://localhost:8000/health"
```

## API 接口

### `GET /scrape`

完整抓取，返回 `DemandReport` 格式。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `keyword` | string | 必填 | 搜索关键词 |
| `time_filter` | string | `month` | 时间范围：`hour` / `day` / `week` / `month` / `year` |
| `include_comments` | bool | `true` | 是否抓取评论 |
| `limit` | int | `100` | 帖子数量限制 |

**返回示例：**

```json
{
  "keyword": "startup pain points",
  "generatedAt": "2026-03-31T07:00:00.000000",
  "sources": [{"name": "Reddit", "type": "reddit"}],
  "trendScore": 6.5,
  "trendLabel": "Rising",
  "quotes": [
    {
      "source": "Reddit",
      "author": "u/username",
      "text": "I've been struggling with..."
    }
  ],
  "painPoints": [
    "Users struggle with startup pain points related workflows.",
    "Current startup pain points solutions frustrate users."
  ],
  "productIdeas": [
    {
      "title": "startup pain points Signal Monitor",
      "description": "Aggregate and analyze startup pain points discussions.",
      "targetUser": "Founders and product teams"
    }
  ],
  "opportunityScore": 7.2,
  "metrics": {
    "demand": 6.5,
    "competition": 4.2,
    "monetization": 7.8
  }
}
```

### `GET /quotes`

只返回 `QuoteItem[]` 数组。

**参数：** `keyword`, `time_filter`, `limit`

### `GET /pain-points`

只返回痛点列表。

**参数：** `keyword`, `time_filter`

## 服务器部署

### Docker（推荐）

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 git 并下载 YARS
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/datavorous/YARS.git /app/YARS

COPY src/ .

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

构建运行：

```bash
docker build -t demand-radar .
docker run -d -p 8000:8000 demand-radar
```

### 直接部署

```bash
# 后台运行
nohup python api_server.py > api.log 2>&1 &

# 或使用 systemd
# /etc/systemd/system/demand-radar.service
[Unit]
Description=Demand Radar Reddit API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/demand-radar/src
ExecStart=/opt/demand-radar/src/venv/bin/python api_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## 项目结构

```
demand-radar-reddit/
├── README.md
├── src/
│   ├── api_server.py   # FastAPI 服务入口
│   ├── scraper.py      # Reddit 爬虫逻辑
│   ├── install.sh      # 一键安装脚本
│   └── requirements.txt # Python 依赖
└── YARS/               # Reddit 爬虫库（install.sh 自动下载）
```

## 命令行使用

也可以直接运行 `scraper.py`：

```bash
python scraper.py "startup problems" -t month -o result.json -c

# 参数：
#   keyword   - 搜索关键词
#   -t, --time  - 时间范围 (默认 month)
#   -o, --output - 输出文件 (默认 output.json)
#   -c, --comments - 包含评论
```

## 注意事项

- YARS 是第三方爬虫库，频繁请求可能被 Reddit 限制
- 建议添加请求间隔或使用代理
- 生产环境应配置 CORS 白名单

## License

MIT