import json
import requests
from bs4 import BeautifulSoup
from collections import Counter

# ================================
# 1. 네이버 뉴스 API 설정
# ================================

from dotenv import load_dotenv
import os

load_dotenv()

NAVER_CLIENT_ID = os.getenv("client_id")
NAVER_CLIENT_SECRET =  os.getenv("client_secret")


NAVER_URL = "https://openapi.naver.com/v1/search/news.json"

naver_headers = {
    "X-Naver-Client-Id": NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
}


def fetch_naver_news(query: str, display: int = 10, sort: str = "date"):
    """
    네이버 뉴스 API로 특정 키워드의 뉴스 목록 가져오기.
    return: items 리스트 (네이버 원본 JSON의 items 필드)
    """
    params = {
        "query": query,
        "display": display,
        "sort": "date",  # "date": 최신순, "sim": 정확도순
    }

    res = requests.get(NAVER_URL, headers=naver_headers, params=params)
    print(f"[{query}] Naver API Status:", res.status_code)

    if res.status_code != 200:
        print("네이버 API 호출 실패:", res.text)
        raise SystemExit()

    data = res.json()
    items = data.get("items", [])
    print(f"[{query}] 원본 기사 개수:", len(items))
    return items


def clean_html_tags(text: str) -> str:
    """
    네이버 검색 결과 title/description에 섞인 <b> 태그 등 제거
    """
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text()


def build_article_list(items, query: str):
    """
    - originallink가 있으면 우선 사용, 없으면 link 사용
    - '완전 동일한 URL 문자열' 기준으로만 중복 제거
    - 어떤 URL이 몇 번 나왔는지도 출력
    """
    articles = []
    urls = []  # 중복 통계용

    # 1) URL 모으기 (중복 카운트용)
    for item in items:
        raw_url = item.get("originallink") or item.get("link")
        if not raw_url:
            continue
        urls.append(raw_url)

    # 2) URL 중복 통계
    counter = Counter(urls)
    print(f"\n=== [{query}] URL 중복 통계 (원본 URL 기준) ===")
    dup_exist = False
    for url, cnt in counter.items():
        if cnt > 1:
            dup_exist = True
            print(f"- {url} -> {cnt}번 등장")
    if not dup_exist:
        print("  중복된 URL 없음 ✅")

    # 3) 실제 기사 리스트(중복 제거)
    seen = set()
    for item in items:
        title_raw = item.get("title", "")
        title = clean_html_tags(title_raw)

        raw_url = item.get("originallink") or item.get("link")
        if not raw_url:
            print(f"[스킵] URL 없음: {title}")
            continue

        if raw_url in seen:
            print(f"[중복 스킵] {title} ({raw_url})")
            continue
        seen.add(raw_url)

        articles.append({
            "id": len(articles) + 1,
            "query": query,
            "title": title,
            "url": raw_url,
        })

    # 4) 최종 기사 목록 출력
    print(f"\n=== [{query}] 최종 기사 목록 (중복 제거 후) ===")
    for a in articles:
        print(f"  [{a['id']}] {a['title']}")
        print(f"       URL: {a['url']}")

    print(f"\n👉 (중복 제거 후) [{query}] 기사 리스트 개수: {len(articles)}")

    return articles


def main():
    # 여기서 검색할 키워드들을 정해줘
    queries = ["삼성전자"]
    display = 20  # 키워드당 가져올 기사 개수

    all_articles = []

    for q in queries:
        items = fetch_naver_news(query=q, display=display, sort="date")
        article_list = build_article_list(items, query=q)
        all_articles.extend(article_list)

    # 결과를 JSON 파일로 저장 → 2번 파일에서 이걸 읽어서 본문 크롤링에 사용
    output_file = "step1_naver_articles.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 저장 완료: {output_file}")
    print(f"   총 기사 수: {len(all_articles)}")


if __name__ == "__main__":
    main()
