#!/usr/bin/env python3
"""
Reddit 痛点数据 API 服务
供 Vercel 前端调用
"""

import os
import sys
import json
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# 导入爬虫
from scraper import scrape_reddit, RedditScraper, DemandReport

app = FastAPI(
    title="Reddit Pain Points API",
    description="提供 Reddit 数据抓取服务，返回 DemandReport 格式",
    version="1.0.0"
)

# CORS 配置（允许 Vercel 前端调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应改为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "Reddit Pain Points API",
        "version": "1.0.0",
        "endpoints": {
            "/scrape": "GET - 抓取 Reddit 数据",
            "/quotes": "GET - 只返回 quotes",
            "/health": "GET - 健康检查"
        }
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/scrape")
def scrape(
    keyword: str = Query(..., description="搜索关键词"),
    time_filter: str = Query("month", description="时间范围: hour/day/week/month/year"),
    include_comments: bool = Query(True, description="是否包含评论"),
    limit: int = Query(100, description="帖子数量限制")
):
    """
    抓取 Reddit 数据，返回完整 DemandReport
    
    返回格式匹配 Vercel 项目 demand-report.ts 类型定义
    """
    try:
        result = scrape_reddit(keyword, time_filter, include_comments)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.get("/quotes")
def get_quotes(
    keyword: str = Query(..., description="搜索关键词"),
    time_filter: str = Query("month", description="时间范围"),
    limit: int = Query(50, description="返回数量")
):
    """
    只返回 QuoteItem[] 格式的数据
    
    供 providers/reddit.ts 调用
    """
    try:
        scraper = RedditScraper()
        posts = scraper.scrape_posts(keyword, time_filter, limit)
        quotes = scraper.generate_quotes(posts, include_comments=True)
        
        return JSONResponse(content={
            "keyword": keyword,
            "count": len(quotes),
            "quotes": [q.to_dict() for q in quotes]
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")


@app.get("/pain-points")
def get_pain_points(
    keyword: str = Query(..., description="搜索关键词"),
    time_filter: str = Query("month", description="时间范围")
):
    """
    只返回痛点列表
    """
    try:
        scraper = RedditScraper()
        posts = scraper.scrape_posts(keyword, time_filter)
        quotes = scraper.generate_quotes(posts[:10])
        pain_points = scraper.extract_pain_points(quotes, keyword)
        
        return JSONResponse(content={
            "keyword": keyword,
            "painPoints": pain_points
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")


# 本地测试入口
if __name__ == "__main__":
    print("启动 Reddit API 服务...")
    print("测试: curl 'http://localhost:8000/scrape?keyword=startup+problems'")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )