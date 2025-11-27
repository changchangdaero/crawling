import json
import time
from openai import OpenAI

from dotenv import load_dotenv
import os

# .env 로드
load_dotenv()

# ================================
# 0. OpenAI (GPT-4o-mini) 설정
# ================================

api_key = os.getenv("gpt_key")
if not api_key:
    raise RuntimeError("❌ .env 에 gpt_key 값이 없습니다. .env 파일을 확인하세요.")

# ✅ 여기서 진짜 클라이언트 객체 생성
client = OpenAI(api_key=api_key)

OPENAI_MODEL_NAME = "gpt-4o-mini"


# ================================
# 1. 입출력 파일 경로
# ================================

INPUT_FILE = "step2_articles_with_content.json"  # 2단계 결과 (본문 포함)
OUTPUT_FILE = "step3_articles_with_summary_and_groups.json"  # 3단계 결과

# 한 기사당 본문을 전부 넣으면 너무 길어질 수 있으니, 앞부분만 잘라서 보냄
MAX_CONTENT_CHARS = 1200


def load_articles(input_file: str):
    """
    step2에서 만든 기사 + 본문 리스트 JSON 불러오기.
    구조: [{id, query, title, url, content}, ...]
    """
    with open(input_file, "r", encoding="utf-8") as f:
        articles = json.load(f)
    print(f"📥 요약/그룹핑 대상 기사 개수: {len(articles)}")
    return articles


def build_brief_articles(articles):
    """
    LLM에 넘길 간략 버전 리스트 만들기.
    - id, title, url, content_snippet 만 포함
    - content_snippet: 본문 앞 MAX_CONTENT_CHARS 글자
    """
    brief_list = []
    for a in articles:
        content = (a.get("content") or "").strip()
        if len(content) > MAX_CONTENT_CHARS:
            content_snippet = content[:MAX_CONTENT_CHARS] + "\n...(이하 생략)"
        else:
            content_snippet = content

        brief_list.append(
            {
                "id": a.get("id"),
                "title": a.get("title"),
                "url": a.get("url"),
                "content": content_snippet,
            }
        )
    return brief_list


def extract_json_from_text(text: str):
    """
    LLM이 혹시 모르게 앞뒤에 뻘소리를 조금 붙여도,
    중간의 JSON 객체만 잘라서 파싱하도록 하는 보조 함수.
    (그래도 프롬프트에서 JSON만 출력하라고 빡세게 말해둠)
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON 형식이 감지되지 않음")
    sliced = text[start : end + 1]
    return json.loads(sliced)


def summarize_and_group_with_llm(brief_articles):
    """
    여러 기사 정보를 한 번에 LLM에 넘겨서:
    1) 각 기사 summary_ko 생성
    2) 내용이 유사하거나 사실상 같은 기사끼리 그룹핑 정보 생성

    👉 여기서 GPT-4o-mini를 사용.
    """

    articles_json = json.dumps(brief_articles, ensure_ascii=False, indent=2)

    prompt = f"""
너는 한국어 뉴스 기사의 감정분석 전처리를 담당하는 도우미야.

아래 JSON 배열 articles에는 여러 뉴스 기사 정보가 들어 있다.
각 원소에는 id, title, url, content 가 있다.
content 는 기사 본문 전체 혹은 앞부분이다.

articles:
{articles_json}

너의 역할은 두 가지다.

1) 각 기사에 대해 감정분석에 쓰기 좋은 요약 summary_ko를 생성한다.
   - summary_ko는 한국어 문장으로 작성한다.
   - 문장 수는 자유지만, 너무 길지 않게 1~4문장 정도로 간결하게 작성한다.
   - 인사말이나 자기소개 없이 바로 요약 내용으로 시작한다.
   - 기사에서 말하는 핵심 사건/주제, 관련 기업/인물/기관, 주요 수치(투자 규모, 실적, 손실 등)가 있으면 가능한 포함한다.
   - 기사 전체의 톤(호재, 악재, 우려, 갈등, 중립적 분석 등)이 드러나도록 쓴다.
   - 새로운 의견을 만들어내지 말고, 기사에 실제로 등장하는 평가/분위기만 반영한다.
   - 문장은 모두 평서형으로 끝낸다.

2) 서로 내용이 실질적으로 동일하거나, 같은 뉴스 이벤트를 약간 다른 표현으로 전하는 중복 기사들을 그룹으로 묶는다.
   - 같은 기업/인물/사건/날짜/수치 등을 공유하며, 사실상 같은 뉴스를 반복 보도한 것으로 판단되면 같은 그룹에 넣는다.
   - 제목이 다르더라도, 내용이 같은 사건을 다루면 같은 그룹이다.
   - 한 그룹은 2개 이상의 기사 id를 포함해야 한다. (1개만 있으면 그룹으로 만들지 않는다.)
   - 서로 겹치지 않는 단독 기사는 그룹에 포함시키지 않는다.

반드시 아래 형식의 JSON만 출력하라. 다른 설명 문장은 절대 출력하지 마라.

{{
  "articles": [
    {{
      "id": 1,
      "summary_ko": "이곳에 id=1 기사에 대한 요약 문장"
    }},
    {{
      "id": 2,
      "summary_ko": "이곳에 id=2 기사에 대한 요약 문장"
    }}
    // 모든 기사에 대해 1개씩 id, summary_ko 쌍을 넣는다.
  ],
  "groups": [
    {{
      "group_id": 1,
      "article_ids": [1, 3, 5],
      "reason": "예: 삼성전자 사장단 인사 발표를 다룬 중복 기사들"
    }},
    {{
      "group_id": 2,
      "article_ids": [2, 4],
      "reason": "예: 같은 반도체 투자 계약 관련 기사들"
    }}
    // 중복 기사가 없다면 groups는 빈 배열 [] 로 둔다.
  ]
}}
"""

    # OpenAI Chat Completions API 호출 (GPT-4o-mini)
    completion = client.chat.completions.create(
        model=OPENAI_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "너는 한국어 뉴스 기사의 요약과 중복 기사 그룹핑을 위한 도우미야. 반드시 JSON만 출력해.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
    )

    content = completion.choices[0].message.content.strip()
    if not content:
        raise RuntimeError("LLM 응답이 비어 있음")

    try:
        parsed = extract_json_from_text(content)
    except Exception as e:
        print("⚠️ LLM JSON 파싱 실패, 원문 일부 출력:")
        print(content[:500])
        raise e

    return parsed


def main():
    # 1) 기사 + 본문 로드
    articles = load_articles(INPUT_FILE)

    if not articles:
        print("⚠️ 처리할 기사가 없습니다.")
        return

    # 2) LLM에 넘길 간단 버전 생성
    brief_articles = build_brief_articles(articles)

    print("\n=== GPT-4o-mini 요약 + 중복 그룹핑 호출 ===")
    print(f"   전달할 기사 수: {len(brief_articles)}")
    time.sleep(0.5)

    # 3) LLM 호출
    result = summarize_and_group_with_llm(brief_articles)

    # result 예시:
    # {
    #   "articles": [{"id": 1, "summary_ko": "..."} ...],
    #   "groups": [{"group_id": 1, "article_ids": [...], "reason": "..."} ...]
    # }

    # GPT 응답에서 id → summary 매핑 (id를 str로 통일해서 안전하게)
    article_summaries = {
        str(a["id"]): a["summary_ko"] for a in result.get("articles", [])
    }

    # 4) 원래 기사 리스트에 summary_ko 붙이기
    merged_articles = []
    missing_summary = 0

    for a in articles:
        aid = a.get("id")
        summary = article_summaries.get(str(aid))
        if not summary:
            missing_summary += 1
            summary = ""  # 비어 있으면 나중에 다시 처리해도 됨

        merged_articles.append(
            {
                "id": aid,
                "query": a.get("query"),
                "title": a.get("title"),
                "url": a.get("url"),
                "content": a.get("content"),
                "summary_ko": summary,
            }
        )

    groups = result.get("groups", [])

    # 5) 콘솔에 요약 결과 출력
    print("\n==============================")
    print("=== 기사별 요약 결과 출력 ===")
    print("==============================")
    for a in merged_articles:
        print(f"\n[ID {a['id']}] {a['title']}")
        print(f"URL: {a['url']}")
        if a["summary_ko"]:
            print(f"요약: {a['summary_ko']}")
        else:
            print("요약: (없음)")

    # 6) 콘솔에 그룹핑 결과 출력
    print("\n==============================")
    print("=== 중복 그룹핑 결과 출력 ===")
    print("==============================")
    if not groups:
        print("그룹 없음 (중복 기사 그룹이 생성되지 않았습니다.)")
    else:
        for g in groups:
            gid = g.get("group_id")
            ids = g.get("article_ids", [])
            reason = g.get("reason", "")
            print(f"\n[그룹 {gid}] 기사 ID들: {ids}")
            print(f"이유: {reason}")

    # 7) 최종 결과 저장
    output_data = {
        "articles": merged_articles,
        "groups": groups,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("\n✅ GPT-4o-mini 요약 + 중복 그룹핑 완료")
    print(f"   기사 수: {len(merged_articles)}")
    print(f"   그룹 수: {len(groups)}")
    if missing_summary > 0:
        print(f"   ⚠️ 요약이 비어 있는 기사 수: {missing_summary}")
    print(f"   저장 파일: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
