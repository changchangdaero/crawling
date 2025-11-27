# run_pipeline.py
"""
전체 뉴스 감정 분석 파이프라인 실행 스크립트

1) step1_naver_articles.py
   - 네이버 뉴스 검색 → step1_naver_articles.json

2) step2_articles_with_content.py
   - 기사 본문 크롤링 → step2_articles_with_content.json

3) step3_articles_with_summary_and_groups.py
   - GPT-4o-mini 요약 + 중복 그룹핑 → step3_articles_with_summary_and_groups.json

4) step4_articles_with_sentiment.py
   - KR-FinBERT 감정 점수(0~100) 계산 → step4_articles_with_sentiment.json

5) step5_save_to_db.py
   - step4 결과를 MariaDB(news_articles 테이블)에 저장
"""

import time
import traceback

# 👇 실제 파일 이름 기준 import
from step1_naver_articles import main as step1_main
from step2_articles_with_content import main as step2_main
from step3_articles_with_summary_and_groups import main as step3_main
from step4_articles_with_sentiment import main as step4_main
from step5_save_to_db import main as step5_main  # ✅ 추가


def run_step(step_func, step_name: str):
    """
    각 단계를 공통 포맷으로 실행해주는 헬퍼 함수.
    """
    print("\n" + "=" * 80)
    print(f"🚀 {step_name} 시작")
    print("=" * 80)

    start = time.time()
    try:
        step_func()
    except Exception:
        print(f"\n💥 {step_name} 실행 중 오류 발생!")
        traceback.print_exc()
        # 여기서 바로 종료
        raise
    else:
        end = time.time()
        print(f"\n✅ {step_name} 완료 (소요 시간: {end - start:.2f}초)")


def main():
    """
    전체 파이프라인 5단계 순차 실행
    """
    # 1단계
    run_step(step1_main, "STEP 1 - 네이버 뉴스 검색 (step1_naver_articles.py)")

    # 2단계
    run_step(step2_main, "STEP 2 - 기사 본문 크롤링 (step2_articles_with_content.py)")

    # 3단계
    run_step(
        step3_main,
        "STEP 3 - LLM 요약 + 중복 그룹핑 (step3_articles_with_summary_and_groups.py)",
    )

    # 4단계
    run_step(
        step4_main,
        "STEP 4 - 감정 점수(0~100) 계산 (step4_articles_with_sentiment.py)",
    )

    # 5단계 ✅ DB 저장
    run_step(
        step5_main,
        "STEP 5 - DB 저장 (step5_save_to_db.py)",
    )

    print("\n" + "=" * 80)
    print("🎉 전체 파이프라인 완료!")
    print("   최종 JSON: step4_articles_with_sentiment.json")
    print("   DB 테이블: test.news_articles (로컬 기준)")
    print("=" * 80)


if __name__ == "__main__":
    main()
