import json
import time
from newspaper import Article

# ================================
# 1. 입출력 파일 설정
# ================================

INPUT_FILE = "step1_naver_articles.json"          # 1단계에서 만든 파일 (id, query, title, url)
OUTPUT_FILE = "step2_articles_with_content.json"  # 본문까지 포함한 결과 파일

# ================================
# 2. 본문 크롤링 함수 (newspaper3k)
# ================================
def get_full_text(url: str) -> str:
    """
    기사 URL에서 newspaper3k로 본문 전체를 가져옴.
    실패하면 ""(빈 문자열) 리턴.
    """
    try:
        article = Article(url, language="ko")
        article.download()
        article.parse()
        text = (article.text or "").strip()
        return text
    except Exception as e:
        print(f"[경고] 본문 크롤링 실패: {url}")
        print("       사유:", e)
        return ""


# ================================
# 3. step1 결과 불러오기
# ================================
def load_articles(input_file: str):
    """
    step1에서 만든 JSON 파일 로드.
    구조 예시: [{id, query, title, url}, ...]
    """
    with open(input_file, "r", encoding="utf-8") as f:
        articles = json.load(f)
    print(f"📥 로드한 기사 개수: {len(articles)}")
    return articles


# ================================
# 4. 각 기사에 본문(content) 붙이기
# ================================
def crawl_contents(articles):
    """
    각 기사에 대해 url로 본문 크롤링해서 "content" 필드 추가.
    """
    results = []
    total = len(articles)

    for idx, a in enumerate(articles, start=1):
        url = a.get("url")
        title = a.get("title")

        print("\n==============================")
        print(f"[{idx}/{total}] 제목: {title}")
        print(f"URL: {url}")

        if not url:
            print("[스킵] URL 없음")
            content = ""
        else:
            content = get_full_text(url)

        if content:
            print(f"[본문 길이] {len(content)}자")
        else:
            print("[본문 없음 또는 크롤링 실패]")

        # step2 형식: id, query, title, url, content
        results.append(
            {
                "id": a.get("id"),
                "query": a.get("query"),
                "title": title,
                "url": url,
                "content": content,
            }
        )

        # 너무 빠르게 연달아 긁으면 막힐 수도 있으니 살짝 쉬어가기 (원하면 주석 처리해도 됨)
        time.sleep(0.5)

    return results


# ================================
# 5. 메인 실행부
# ================================
def main():
    # 1) step1 결과 로드
    articles = load_articles(INPUT_FILE)
    if not articles:
        print("⚠️ 처리할 기사가 없습니다.")
        return

    # 2) 본문 크롤링
    print("\n=== 네이버 기사 본문 크롤링 시작 (newspaper3k) ===")
    articles_with_content = crawl_contents(articles)

    # 3) 결과 저장
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles_with_content, f, ensure_ascii=False, indent=2)

    print("\n✅ 본문 크롤링 완료")
    print(f"   총 기사 수: {len(articles_with_content)}")
    print(f"   저장 파일: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
