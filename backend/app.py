import os
import re
import json
import time
import logging
from datetime import datetime, timezone
from typing import List, Literal, Optional

import praw
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

load_dotenv()

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("reddit-pain-analyzer")

# =========================
# App
# =========================
app = FastAPI(title="Demand Radar - Reddit Pain Point Analyzer", version="4.0")

ALLOWED_ORIGINS = [
    "https://fast-get-market-requestments.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Environment
# =========================
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "").strip()
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "DemandRadar:v4.0 (by u/your_username)").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
    logger.warning("Reddit credentials are missing.")

if not OPENAI_API_KEY:
    logger.warning("OpenAI API key is missing.")

# =========================
# Clients
# =========================
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT,
    check_for_async=False,
)

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# Models
# =========================
PainCategory = Literal["功能缺失", "竞品不满", "使用体验", "定价", "其他"]
CommentSortType = Literal["best", "top", "new", "controversial", "confidence"]

class AnalyzeRedditRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=120, description="搜索关键词")
    subreddits: List[str] = Field(
        default_factory=lambda: ["SaaS", "indiehackers", "Entrepreneur", "Fitness", "loseit"]
    )
    max_posts: int = Field(default=20, ge=1, le=80)
    per_query_limit: int = Field(default=8, ge=1, le=20)
    time_filter: Literal["day", "week", "month", "year", "all"] = "month"
    comment_sort: CommentSortType = "best"
    max_top_level_comments: int = Field(default=8, ge=3, le=20)
    max_replies_per_top_comment: int = Field(default=2, ge=0, le=5)

class PainPointItem(BaseModel):
    pain_point: str
    strength_score: int = Field(ge=0, le=100)
    category: PainCategory
    original_quote: str
    why_important: str

class LLMPainPointResult(BaseModel):
    pain_points: List[PainPointItem] = Field(default_factory=list)

class PainPointResponseItem(BaseModel):
    subreddit: str
    url: str
    title: str
    pain_point: str
    strength_score: int
    category: str
    original_quote: str
    why_important: str
    upvotes: int
    comments_count: int
    created: str

class AnalyzeRedditResponse(BaseModel):
    status: Literal["success"]
    keyword: str
    total_found: int
    pain_points: List[PainPointResponseItem]
    analyzed_at: str

# =========================
# Config
# =========================
PAIN_KEYWORDS = [
    "wish",
    "need a tool",
    "need something",
    "frustrated",
    "frustrating",
    "struggling",
    "annoying",
    "sucks",
    "pain point",
    "better way",
    "anyone else",
    "problem",
    "hard to",
    "tedious",
    "manual",
    "hate",
    "difficult",
]

# =========================
# Helpers
# =========================
def normalize_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"\s+", " ", text).strip()
    return text

def safe_excerpt(text: str, max_len: int) -> str:
    return normalize_text(text)[:max_len]

def is_removed_or_deleted(text: str) -> bool:
    t = normalize_text(text).lower()
    return t in {"[deleted]", "[removed]"} or not t

def seems_pain_related(text: str) -> bool:
    text_lower = (text or "").lower()
    return any(kw in text_lower for kw in PAIN_KEYWORDS)

def keyword_related(text: str, keyword: str) -> bool:
    return keyword.lower() in (text or "").lower()

def dedupe_items(items: List[PainPointResponseItem]) -> List[PainPointResponseItem]:
    seen = set()
    result = []
    for item in items:
        key = (
            item.subreddit.lower(),
            item.pain_point.strip().lower(),
            item.original_quote.strip().lower()[:180],
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result

def build_search_queries(keyword: str) -> List[str]:
    keyword = keyword.strip()
    # 查询篮子：提高命中真实痛点帖的概率
    return [
        keyword,
        f'{keyword} "frustrated"',
        f'{keyword} "wish"',
        f'{keyword} "problem"',
        f'{keyword} "better way"',
    ]

def select_high_value_comments(
    submission,
    comment_sort: str,
    max_top_level_comments: int = 8,
    max_replies_per_top_comment: int = 2,
) -> str:
    """
    精准评论采样策略：
    1) 先设置 comment_sort
    2) replace_more(limit=0) 只去掉 MoreComments 占位符，不做深层全量展开
    3) 优先顶级评论（top-level）
    4) 每个顶级评论最多抽少量高价值回复
    """
    try:
        submission.comment_sort = comment_sort
        submission.comment_limit = max_top_level_comments
        submission.comments.replace_more(limit=0)
    except Exception as e:
        logger.warning(f"replace_more failed for submission={submission.id}: {e}")
        return ""

    top_level = []
    for c in submission.comments:
        body = normalize_text(getattr(c, "body", ""))
        score = int(getattr(c, "score", 0) or 0)

        if is_removed_or_deleted(body):
            continue
        if len(body) < 20:
            continue

        top_level.append((score, c, body))

    # 高赞顶级评论优先
    top_level.sort(key=lambda x: x[0], reverse=True)
    top_level = top_level[:max_top_level_comments]

    collected = []

    for idx, (score, comment, body) in enumerate(top_level, start=1):
        collected.append(f"顶级评论{idx}（赞同 {score}）: {body}")

        # 从该顶级评论里抽少量高价值回复
        replies = []
        try:
            for reply in getattr(comment, "replies", []):
                reply_body = normalize_text(getattr(reply, "body", ""))
                reply_score = int(getattr(reply, "score", 0) or 0)

                if is_removed_or_deleted(reply_body):
                    continue
                if len(reply_body) < 20:
                    continue

                # 回复更严格：要么高赞，要么明显是痛点表达
                if reply_score >= 2 or seems_pain_related(reply_body):
                    replies.append((reply_score, reply_body))
        except Exception:
            pass

        replies.sort(key=lambda x: x[0], reverse=True)
        replies = replies[:max_replies_per_top_comment]

        for j, (reply_score, reply_body) in enumerate(replies, start=1):
            collected.append(f"  ↳ 回复{idx}.{j}（赞同 {reply_score}）: {reply_body}")

    return "\n".join(collected)

def analyze_thread_with_llm(
    keyword: str,
    post_title: str,
    post_text: str,
    comments_text: str,
) -> LLMPainPointResult:
    """
    这里为了你“直接可运行”，采用兼容性更好的 json_object。
    后面可以升级成 Structured Outputs。
    """
    prompt = f"""
你是一个专业的市场研究员，专门从 Reddit 帖子和评论中提炼真实用户痛点。

目标关键词：{keyword}

帖子标题：
{post_title}

帖子内容：
{post_text}

评论内容：
{comments_text}

任务：
请提炼最真实、最具体的 1-3 个痛点。

输出要求：
1. 只输出 JSON
2. JSON 格式必须是：
{{
  "pain_points": [
    {{
      "pain_point": "简短痛点描述（一句话）",
      "strength_score": 85,
      "category": "功能缺失 | 竞品不满 | 使用体验 | 定价 | 其他",
      "original_quote": "用户原句",
      "why_important": "为什么这是真实痛点（1-2句）"
    }}
  ]
}}
3. 如果没有明显痛点，返回 {{"pain_points": []}}
4. original_quote 必须尽量来自输入中的真实句子，不要凭空编造
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            max_tokens=700,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "你是严谨的市场研究员，只输出有效 JSON。"},
                {"role": "user", "content": prompt},
            ],
        )

        content = response.choices[0].message.content or '{"pain_points": []}'
        parsed = json.loads(content)
        raw_points = parsed.get("pain_points", [])

        if not isinstance(raw_points, list):
            return LLMPainPointResult(pain_points=[])

        normalized = []
        for item in raw_points[:3]:
            try:
                category = item.get("category", "其他")
                if category not in {"功能缺失", "竞品不满", "使用体验", "定价", "其他"}:
                    category = "其他"

                normalized.append(
                    PainPointItem(
                        pain_point=safe_excerpt(item.get("pain_point", ""), 180),
                        strength_score=max(0, min(100, int(item.get("strength_score", 0)))),
                        category=category,
                        original_quote=safe_excerpt(item.get("original_quote", ""), 400),
                        why_important=safe_excerpt(item.get("why_important", ""), 300),
                    )
                )
            except Exception:
                continue

        return LLMPainPointResult(pain_points=normalized)
    except Exception as e:
        logger.exception(f"LLM analysis failed: {e}")
        return LLMPainPointResult(pain_points=[])

def should_keep_submission(title: str, selftext: str, comments_text: str, keyword: str) -> bool:
    full_text = f"{title} {selftext}"
    # 至少满足：关键词相关，且帖子或评论像是在讨论问题/痛点
    return (
        keyword_related(full_text, keyword)
        or keyword_related(comments_text, keyword)
        or (seems_pain_related(full_text) and keyword)
        or (seems_pain_related(comments_text) and keyword)
    )

# =========================
# Routes
# =========================
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat()
    }

@app.post("/api/analyze-reddit", response_model=AnalyzeRedditResponse)
async def analyze_reddit(request: AnalyzeRedditRequest):
    keyword = request.keyword.strip().lower()
    if not keyword:
        raise HTTPException(status_code=400, detail="请输入关键词")

    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Reddit credentials are not configured")

    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API key is not configured")

    logger.info(f"[analyze-reddit] start keyword={keyword}")

    all_pain_points: List[PainPointResponseItem] = []
    processed_posts = 0
    seen_submission_ids = set()

    queries = build_search_queries(keyword)

    for sub_name in request.subreddits:
        if processed_posts >= request.max_posts:
            break

        try:
            subreddit = reddit.subreddit(sub_name)

            for query in queries:
                if processed_posts >= request.max_posts:
                    break

                logger.info(f"[reddit] searching r/{sub_name} query={query}")

                for submission in subreddit.search(
                    query=query,
                    sort="relevance",
                    time_filter=request.time_filter,
                    syntax="lucene",
                    limit=request.per_query_limit,
                ):
                    if processed_posts >= request.max_posts:
                        break

                    if submission.id in seen_submission_ids:
                        continue
                    seen_submission_ids.add(submission.id)

                    title = normalize_text(submission.title)
                    selftext = normalize_text(submission.selftext or "")

                    # 基础质量门槛
                    if int(submission.score or 0) < 2 and int(submission.num_comments or 0) < 2:
                        continue

                    comments_text = select_high_value_comments(
                        submission=submission,
                        comment_sort=request.comment_sort,
                        max_top_level_comments=request.max_top_level_comments,
                        max_replies_per_top_comment=request.max_replies_per_top_comment,
                    )

                    if not comments_text:
                        continue

                    if not should_keep_submission(title, selftext, comments_text, keyword):
                        continue

                    llm_result = analyze_thread_with_llm(
                        keyword=keyword,
                        post_title=safe_excerpt(title, 300),
                        post_text=safe_excerpt(selftext, 1000),
                        comments_text=safe_excerpt(comments_text, 2200),
                    )

                    for pp in llm_result.pain_points:
                        all_pain_points.append(
                            PainPointResponseItem(
                                subreddit=f"r/{sub_name}",
                                url=f"https://reddit.com{submission.permalink}",
                                title=title,
                                pain_point=pp.pain_point,
                                strength_score=pp.strength_score,
                                category=pp.category,
                                original_quote=pp.original_quote,
                                why_important=pp.why_important,
                                upvotes=int(submission.score or 0),
                                comments_count=int(submission.num_comments or 0),
                                created=datetime.fromtimestamp(
                                    submission.created_utc, tz=timezone.utc
                                ).strftime("%Y-%m-%d"),
                            )
                        )

                    processed_posts += 1
                    time.sleep(1.0)

        except Exception as e:
            logger.exception(f"Error while processing subreddit r/{sub_name}: {e}")
            continue

    all_pain_points = dedupe_items(all_pain_points)
    all_pain_points.sort(key=lambda x: x.strength_score, reverse=True)

    result = AnalyzeRedditResponse(
        status="success",
        keyword=keyword,
        total_found=len(all_pain_points),
        pain_points=all_pain_points[:30],
        analyzed_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )

    logger.info(f"[analyze-reddit] finish keyword={keyword} total_found={result.total_found}")
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)