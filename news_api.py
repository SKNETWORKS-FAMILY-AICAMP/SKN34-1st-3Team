"""
news_api.py
===========
네이버 뉴스 검색 API를 이용해 추천 차량/브랜드 관련 최신 자동차 뉴스를 가져옴
"""

from __future__ import annotations

import html
import os
import re
from email.utils import parsedate_to_datetime

import requests
from dotenv import load_dotenv

load_dotenv()

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


def has_naver_news_keys() -> bool:
    """네이버 뉴스 API 호출에 필요한 환경변수가 있는지 확인"""
    return bool(os.getenv("NAVER_CLIENT_ID") and os.getenv("NAVER_CLIENT_SECRET"))


def _clean_html(text: str) -> str:
    """네이버 API 응답의 <b> 태그와 HTML 엔티티 제거"""
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _format_pub_date(pub_date: str) -> str:
    """네이버 pubDate 형식을 화면에 보기 좋은 형태로 변환"""
    if not pub_date:
        return ""

    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return pub_date


def build_news_query(brands: list[str], car_models: list[str] | None = None) -> str:
    """
    추천 브랜드/차량명을 기반으로 뉴스 검색어 생성

    예:
      brands=["테슬라", "BMW"], car_models=["Model 3"]
      -> "테슬라 BMW Model 3 자동차"
    """
    keywords: list[str] = []

    for brand in brands[:3]:
        if brand and brand not in keywords:
            keywords.append(str(brand))

    if car_models:
        for model in car_models[:2]:
            if model and model not in keywords:
                keywords.append(str(model))

    if not keywords:
        keywords.append("자동차")

    return " ".join(keywords) + " 자동차"


def fetch_naver_news(query: str, display: int = 6, sort: str = "date") -> list[dict]:
    """
    네이버 뉴스 검색 API 호출

    sort:
      - "date": 날짜순
      - "sim": 정확도순
    """
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")

    if not client_id or not client_secret:
        return []

    display = min(max(int(display), 1), 100)

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {
        "query": query,
        "display": display,
        "start": 1,
        "sort": sort,
    }

    response = requests.get(
        NAVER_NEWS_URL,
        headers=headers,
        params=params,
        timeout=8,
    )
    response.raise_for_status()

    articles: list[dict] = []
    seen_links: set[str] = set()

    for item in response.json().get("items", []):
        link = item.get("originallink") or item.get("link")
        if not link or link in seen_links:
            continue

        seen_links.add(link)

        articles.append(
            {
                "title": _clean_html(item.get("title", "")),
                "description": _clean_html(item.get("description", "")),
                "link": link,
                "naver_link": item.get("link", ""),
                "published_at": _format_pub_date(item.get("pubDate", "")),
            }
        )

    return articles