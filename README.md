# Demand Radar - Reddit

通过关键词从 Reddit 社区挖掘用户痛点需求，帮助产品开发者发现真实市场机会。

## 功能

- 🔍 多 Subreddit 并行搜索
- 🏷️ LLM 自动分类痛点（功能缺失 / 竞品不满 / 使用体验 / 定价 / 其他）
- 📊 强度评分 0-100
- 💬 抓取高价值评论
- 🚀 Docker 一键部署

## 快速部署

### Docker

```bash
cd backend
cp .env.example .env
# 编辑 .env 填入你的 Reddit API 和 OpenAI API Key
docker build -t demand-radar .
docker run -d -p 8000:8000 --env-file backend/.env demand-radar
```

### 本地

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## API

**POST /analyze**

```json
{
  "keyword": "meal prep",
  "subreddits": ["fitness", "loseit", "MealPrepSunday"],
  "max_posts": 20,
  "time_filter": "month",
  "comment_sort": "best",
  "max_top_level_comments": 8,
  "max_replies_per_top_comment": 2
}
```

**GET /health** — 健康检查

## 环境变量

| 变量 | 说明 |
|------|------|
| `REDDIT_CLIENT_ID` | Reddit App Client ID |
| `REDDIT_CLIENT_SECRET` | Reddit App Secret |
| `REDDIT_USER_AGENT` | Reddit User Agent |
| `OPENAI_API_KEY` | OpenAI API Key |
| `OPENAI_MODEL` | 模型，默认 `gpt-4o-mini` |

Reddit API 申请：[reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
