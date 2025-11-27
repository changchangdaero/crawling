import json
from transformers import pipeline
from dotenv import load_dotenv
import os

# ================================
# 0. .env에서 HF 토큰 읽기
# ================================
load_dotenv()  # .env 파일 로드

HF_TOKEN = os.getenv("huggingface_api_token")  # .env에 있는 키 이름이 hf_token이라고 가정
if not HF_TOKEN:
    raise RuntimeError("❌ .env 파일에 hf_token 이 없습니다. hfcl_token=... 형태로 추가해 주세요.")

# ================================
# 1. 감정분석 모델 설정
# ================================
MODEL_NAME = "DataWizardd/finbert-sentiment-ko"

print(f"📦 감정분석 모델 로딩 중: {MODEL_NAME}")
sentiment_pipe = pipeline(
    "text-classification",
    model=MODEL_NAME,
    token=HF_TOKEN,      # ✅ 여기서 HF 토큰 사용
    top_k=None,          # return_all_scores=True 대신 권장 방식
)

# ================================
# 2. 입출력 파일
# ================================
INPUT_FILE = "step3_articles_with_summary_and_groups.json"  # 3단계 결과
OUTPUT_FILE = "step4_articles_with_sentiment.json"          # 4단계 최종 결과


def load_step3(input_file: str):
    """
    step3 결과 파일 구조:
    {
      "articles": [ {...}, {...}, ... ],
      "groups": [ {...}, {...}, ... ]
    }
    """
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    articles = data.get("articles", [])
    groups = data.get("groups", [])

    print(f"📥 기사 개수: {len(articles)}")
    print(f"📥 그룹 개수: {len(groups)}")

    return articles, groups


def compute_k_index(p_pos: float, p_neu: float, p_neg: float):
    """
    0~100 점수 계산:

    base = 긍정 - 부정
    confidence = 1 - 중립
    S = base * confidence
    score = (S + 1) / 2 * 100
    """

    base = p_pos - p_neg          # 긍정 - 부정
    confidence = 1.0 - p_neu      # 1 - 중립
    S = base * confidence
    raw_score = (S + 1.0) / 2.0 * 100.0
    score = max(0.0, min(100.0, raw_score))  # 0~100 클램프

    if score >= 80:
        zone = "강한 매수 감정 (FOMO/과열 가능 구간)"
    elif score >= 60:
        zone = "매수 우위"
    elif score >= 40:
        zone = "중립 구간"
    elif score >= 20:
        zone = "매수 비추천"
    else:
        zone = "강한 매수 금지"

    return score, zone


def analyze_sentiment(text: str):
    """
    텍스트 하나 받아서 감정분석 실행 + 0~100 지표 계산.
    """
    if not text or not text.strip():
        return {
            "label": "UNKNOWN",
            "raw_score": 0.0,
            "prob_positive": 0.0,
            "prob_neutral": 1.0,
            "prob_negative": 0.0,
            "sentiment_index": 50.0,
            "sentiment_zone": "데이터 없음",
        }

    snippet = text.strip()
    if len(snippet) > 512:
        snippet = snippet[:512]

    try:
        # top_k=None → 모든 라벨 확률 반환
        # 결과 형태: [[{"label": "...", "score": ...}, ...]]
        outputs = sentiment_pipe(snippet, truncation=True)[0]
    except Exception as e:
        print(f"   ⚠️ 감정분석 중 오류 발생: {e}")
        return {
            "label": "ERROR",
            "raw_score": 0.0,
            "prob_positive": 0.0,
            "prob_neutral": 1.0,
            "prob_negative": 0.0,
            "sentiment_index": 50.0,
            "sentiment_zone": "오류",
        }

    p_pos = 0.0
    p_neu = 0.0
    p_neg = 0.0

    for item in outputs:
        label = item.get("label", "")
        score = float(item.get("score", 0.0))

        if label in ["긍정", "positive", "POSITIVE", "LABEL_2"]:
            p_pos = score
        elif label in ["중립", "neutral", "NEUTRAL", "LABEL_1"]:
            p_neu = score
        elif label in ["부정", "negative", "NEGATIVE", "LABEL_0"]:
            p_neg = score

    if (p_pos + p_neu + p_neg) == 0.0:
        best = max(outputs, key=lambda x: x.get("score", 0.0))
        p_pos = float(best.get("score", 1.0))
        p_neu = 0.0
        p_neg = 0.0

    best_label_item = max(outputs, key=lambda x: x.get("score", 0.0))
    best_label = best_label_item.get("label", "UNKNOWN")
    best_score = float(best_label_item.get("score", 0.0))

    sentiment_index, sentiment_zone = compute_k_index(p_pos, p_neu, p_neg)

    return {
        "label": best_label,
        "raw_score": best_score,
        "prob_positive": p_pos,
        "prob_neutral": p_neu,
        "prob_negative": p_neg,
        "sentiment_index": sentiment_index,
        "sentiment_zone": sentiment_zone,
    }


def main():
    articles, groups = load_step3(INPUT_FILE)

    enriched_articles = []

    print("\n=== 감정분석 시작 (KR-FinBERT 기반 0~100 지표 계산) ===")

    for idx, a in enumerate(articles, start=1):
        aid = a.get("id")
        title = a.get("title")
        summary = (a.get("summary_ko") or "").strip()
        content = (a.get("content") or "").strip()

        print("\n" + "=" * 90)
        print(f"▶ [{idx}/{len(articles)}] ID={aid}")
        print(f"제목: {title}")

        if summary:
            target_text = summary
            print("   → summary_ko 기반 감정분석")
        elif content:
            target_text = content[:512]
            print("   → summary_ko 없음, 본문 앞부분으로 감정분석")
        else:
            target_text = ""
            print("   → 분석할 텍스트 없음, UNKNOWN 처리 예정")

        sentiment_result = analyze_sentiment(target_text)

        print(
            f"   [감정분석 결과] label={sentiment_result['label']}, "
            f"raw={sentiment_result['raw_score']:.4f}, "
            f"index={sentiment_result['sentiment_index']:.2f}, "
            f"zone={sentiment_result['sentiment_zone']}"
        )
        print(
            f"   [확률] 긍정={sentiment_result['prob_positive']:.3f}, "
            f"중립={sentiment_result['prob_neutral']:.3f}, "
            f"부정={sentiment_result['prob_negative']:.3f}"
        )

        enriched = {
            **a,
            "sentiment_label": sentiment_result["label"],
            "sentiment_raw_score": sentiment_result["raw_score"],
            "sentiment_prob_positive": sentiment_result["prob_positive"],
            "sentiment_prob_neutral": sentiment_result["prob_neutral"],
            "sentiment_prob_negative": sentiment_result["prob_negative"],
            "sentiment_index": sentiment_result["sentiment_index"],
            "sentiment_zone": sentiment_result["sentiment_zone"],
        }
        enriched_articles.append(enriched)

    output_data = {
        "articles": enriched_articles,
        "groups": groups,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("\n✅ 감정분석 완료 (0~100 지표 포함)")
    print(f"   총 기사 수: {len(enriched_articles)}")
    print(f"   저장 파일: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
