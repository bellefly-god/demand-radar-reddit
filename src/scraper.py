#!/usr/bin/env python3
"""
Reddit 痛点数据抓取器
返回符合 DemandReport 格式的数据
"""

import sys
import os
import json
import time
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict

# 添加 YARS 路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
YARS_PATH = os.path.join(SCRIPT_DIR, "YARS", "src")
sys.path.insert(0, YARS_PATH)

# ── 强制注入代理 + 完整 Headers 到 YARS ──────────────────────────────────────
import os as _os
_http  = _os.environ.get("HTTP_PROXY")  or _os.environ.get("http_proxy")
_https = _os.environ.get("HTTPS_PROXY") or _os.environ.get("https_proxy")

if _http or _https:
    _proxy = {}
    if _http:  _proxy["http"]  = _http
    if _https: _proxy["https"] = _https

    import requests as _req
    _orig = _req.Session.request
    
    # Reddit 需要完整浏览器 headers 才返回 JSON
    _BROWSER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    
    def _proxied(self, method, url, **kw):
        kw.setdefault("proxies", _proxy)
        # 强制注入完整浏览器 headers
        for k, v in _BROWSER_HEADERS.items():
            self.headers.setdefault(k, v)
        return _orig(self, method, url, **kw)
    
    _req.Session.request = _proxied
    print(f"[代理] YARS 已注入代理 + 浏览器 Headers: {_proxy}")
# ──────────────────────────────────────────────────────────────

from yars.yars import YARS


# 数据类型定义（匹配 Vercel 项目）

@dataclass
class QuoteItem:
    source: str
    text: str
    author: Optional[str] = None

    def to_dict(self) -> Dict:
        d = {"source": self.source, "text": self.text}
        if self.author:
            d["author"] = self.author
        return d


@dataclass
class ReportSource:
    name: str
    type: str  # "ai" | "reddit" | "trends" | "x"


@dataclass
class ProductIdea:
    title: str
    description: str
    targetUser: str


@dataclass  
class OpportunityMetrics:
    demand: float
    competition: float
    monetization: float


@dataclass
class DemandReport:
    keyword: str
    generatedAt: str
    sources: List[ReportSource]
    trendScore: float
    trendLabel: str  # "Rising" | "Stable" | "Declining"
    quotes: List[QuoteItem]
    painPoints: List[str]
    productIdeas: List[ProductIdea]
    opportunityScore: float
    metrics: OpportunityMetrics

    def to_dict(self) -> Dict:
        return {
            "keyword": self.keyword,
            "generatedAt": self.generatedAt,
            "sources": [asdict(s) for s in self.sources],
            "trendScore": self.trendScore,
            "trendLabel": self.trendLabel,
            "quotes": [q.to_dict() for q in self.quotes],
            "painPoints": self.painPoints,
            "productIdeas": [asdict(p) for p in self.productIdeas],
            "opportunityScore": self.opportunityScore,
            "metrics": asdict(self.metrics)
        }


class RedditScraper:
    """Reddit 数据抓取器"""
    
    def __init__(self):
        self.yars = YARS()
        self.reddit_source = ReportSource(name="Reddit", type="reddit")
    
    def scrape_posts(self, keyword: str, time_filter: str = "month", limit: int = 100) -> List[Dict]:
        """抓取帖子 - 使用 YARS 的搜索 API"""
        all_posts = []
        
        # 方式1: 直接搜索 Reddit（优先）
        try:
            print(f"[scrape_posts] 搜索关键词: {keyword}")
            search_results = self.yars.search_reddit(keyword, limit=limit)
            
            for p in search_results:
                title = p.get("title", "")
                link = p.get("link", "")
                description = p.get("description", "")
                
                all_posts.append({
                    "title": title,
                    "description": description,
                    "author": "unknown",
                    "url": link,
                    "score": 0,
                    "num_comments": 0,
                    "created_utc": 0
                })
            print(f"[scrape_posts] 搜索找到 {len(search_results)} 条帖子")
        except Exception as e:
            print(f"[scrape_posts] 搜索错误: {e}")
        
        # 方式2: 在相关 subreddit 搜索（补充）
        target_subreddits = ["SaaS", "indiehackers", "Entrepreneur", "startups", "Business"]
        for subreddit in target_subreddits:
            try:
                results = self.yars.search_subreddit(subreddit, keyword, limit=20)
                for p in results:
                    title = p.get("title", "")
                    if title not in [x["title"] for x in all_posts]:  # 去重
                        all_posts.append({
                            "title": title,
                            "description": p.get("description", ""),
                            "author": "unknown",
                            "url": p.get("link", ""),
                            "score": 0,
                            "num_comments": 0,
                            "created_utc": 0
                        })
            except Exception as e:
                print(f"[scrape_posts] {subreddit} 搜索错误: {e}")
                continue
        
        return all_posts[:limit]  # 限制返回数量
    
    def scrape_comments(self, permalink: str, limit: int = 10) -> List[Dict]:
        """抓取帖子评论"""
        try:
            details = self.yars.scrape_post_details(permalink)
            if details and "comments" in details:
                return details["comments"][:limit]
        except Exception as e:
            print(f"[scrape_comments] 错误: {e}")
        return []
    
    def generate_quotes(self, posts: List[Dict], include_comments: bool = True) -> List[QuoteItem]:
        """从帖子生成 QuoteItem 列表"""
        quotes = []
        
        for post in posts[:20]:  # 最多处理20个帖子
            # 添加帖子本身作为 quote
            text = post.get("description", "") or post.get("title", "")
            if text:
                quotes.append(QuoteItem(
                    source="Reddit",
                    author=f"u/{post.get('author', 'unknown')}",
                    text=text[:500]  # 截断过长内容
                ))
            
            # 抓取评论
            if include_comments and post.get("num_comments", 0) > 0:
                url = post.get("url", "")
                if "reddit.com" in url:
                    permalink = url.split("reddit.com")[1]
                elif url.startswith("/"):
                    permalink = url
                else:
                    permalink = url
                
                comments = self.scrape_comments(permalink, limit=5)
                for c in comments:
                    body = c.get("body", "")
                    if body and len(body) > 20:
                        quotes.append(QuoteItem(
                            source="Reddit",
                            author=f"u/{c.get('author', 'unknown')}",
                            text=body[:300]
                        ))
                
                # 防止请求过快
                time.sleep(0.5)
        
        return quotes
    
    def extract_pain_points(self, quotes: List[QuoteItem], keyword: str) -> List[str]:
        """从 quotes 中提取痛点关键词"""
        pain_keywords = [
            "struggle", "problem", "pain", "frustrating", "annoying",
            "difficult", "hard", "impossible", "broken", "missing",
            "need", "wish", "want", "hope", "dream",
            "too slow", "too expensive", "too complex", "too manual",
            "don't have", "can't find", "no way", "lack of"
        ]
        
        pain_points = []
        combined_text = " ".join([q.text.lower() for q in quotes])
        
        for kw in pain_keywords:
            if kw in combined_text:
                # 根据关键词生成痛点描述
                if kw in ["struggle", "problem", "difficult", "hard"]:
                    pain_points.append(f"Users struggle with {keyword} related workflows.")
                elif kw in ["too slow", "too manual"]:
                    pain_points.append(f"Processes around {keyword} are still too manual and slow.")
                elif kw in ["frustrating", "annoying"]:
                    pain_points.append(f"Current {keyword} solutions frustrate users.")
                elif kw in ["missing", "lack of", "don't have"]:
                    pain_points.append(f"Key features for {keyword} are missing in existing tools.")
                elif kw in ["need", "wish", "want"]:
                    pain_points.append(f"Users explicitly request better {keyword} support.")
        
        # 去重并限制数量
        unique = list(set(pain_points))
        return unique[:5] if unique else [
            f"Users researching '{keyword}' seek clearer validation paths.",
            f"Signal collection for '{keyword}' remains manual and fragmented."
        ]
    
    def calculate_metrics(self, posts: List[Dict], quotes: List[QuoteItem]) -> OpportunityMetrics:
        """计算机会指标"""
        # 基于帖子数量和互动计算
        total_score = sum(p.get("score", 0) for p in posts)
        total_comments = sum(p.get("num_comments", 0) for p in posts)
        quote_count = len(quotes)
        
        # demand: 基于互动量
        demand = min(10, max(1, (total_score / 1000) + (total_comments / 100) + 3))
        
        # competition: 基于帖子数量（越多说明讨论多，竞争可能高）
        competition = min(10, max(1, len(posts) / 10 + 3))
        
        # monetization: 基于痛点数量
        monetization = min(10, max(1, quote_count / 5 + 4))
        
        return OpportunityMetrics(
            demand=round(demand, 1),
            competition=round(competition, 1),
            monetization=round(monetization, 1)
        )
    
    def scrape(self, keyword: str, time_filter: str = "month", include_comments: bool = True) -> DemandReport:
        """完整抓取流程"""
        print(f"[RedditScraper] 开始抓取: {keyword}")
        
        # 1. 抓取帖子
        posts = self.scrape_posts(keyword, time_filter)
        print(f"[RedditScraper] 找到 {len(posts)} 条相关帖子")
        
        # 2. 生成 quotes
        quotes = self.generate_quotes(posts, include_comments)
        print(f"[RedditScraper] 生成 {len(quotes)} 条 quotes")
        
        # 3. 提取痛点
        pain_points = self.extract_pain_points(quotes, keyword)
        
        # 4. 计算指标
        metrics = self.calculate_metrics(posts, quotes)
        
        # 5. 确定趋势
        avg_score = sum(p.get("score", 0) for p in posts) / max(1, len(posts))
        trend_score = min(10, max(1, avg_score / 100 + 5))
        trend_label = "Rising" if avg_score > 500 else "Stable" if avg_score > 100 else "Declining"
        
        # 6. 生成产品创意
        product_ideas = [
            ProductIdea(
                title=f"{keyword} Signal Monitor",
                description=f"Aggregate and analyze {keyword} related discussions and pain points.",
                targetUser="Founders and product teams"
            )
        ]
        if len(pain_points) > 2:
            product_ideas.append(ProductIdea(
                title=f"{keyword} Validation Tool",
                description=f"Help teams validate {keyword} opportunities faster with real user signals.",
                targetUser="Startup founders"
            ))
        
        # 7. 计算总分
        opportunity_score = round((metrics.demand + metrics.monetization) / 2, 1)
        
        # 8. 构建报告
        report = DemandReport(
            keyword=keyword,
            generatedAt=datetime.now().isoformat(),
            sources=[self.reddit_source] if quotes else [],
            trendScore=round(trend_score, 1),
            trendLabel=trend_label,
            quotes=quotes,
            painPoints=pain_points,
            productIdeas=product_ideas,
            opportunityScore=opportunity_score,
            metrics=metrics
        )
        
        print(f"[RedditScraper] 完成: {len(quotes)} quotes, {len(pain_points)} pain points")
        return report


def scrape_reddit(keyword: str, time_filter: str = "month", include_comments: bool = True) -> Dict:
    """便捷函数，返回 dict"""
    scraper = RedditScraper()
    report = scraper.scrape(keyword, time_filter, include_comments)
    return report.to_dict()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("keyword", help="搜索关键词")
    parser.add_argument("-t", "--time", default="month", help="时间范围")
    parser.add_argument("-o", "--output", default="output.json", help="输出文件")
    parser.add_argument("-c", "--comments", action="store_true", help="包含评论")
    
    args = parser.parse_args()
    
    result = scrape_reddit(args.keyword, args.time, args.comments)
    
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"结果保存到: {args.output}")
    print(f"Quotes: {len(result['quotes'])}")
    print(f"Pain points: {len(result['painPoints'])}")