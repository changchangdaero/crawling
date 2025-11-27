# step5_save_to_db.py
import json
import pymysql
from datetime import datetime

# ================================
# 0. DB 접속 설정
# ================================
DB_HOST = "127.0.0.1"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "changmin"
DB_NAME = "test"   # HeidiSQL에서 쓰는 DB 이름

INPUT_FILE = "step4_articles_with_sentiment.json"


def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


# ================================
# 1. 테이블 준비 (ERD 기반 튜닝 버전)
# ================================
def ensure_tables(conn):
    create_companies_sql = """
    CREATE TABLE IF NOT EXISTS Companies (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(50) NOT NULL UNIQUE,
        sector_id BIGINT NULL
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4
      COLLATE=utf8mb4_unicode_ci;
    """

    create_news_sql = """
    CREATE TABLE IF NOT EXISTS News (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(500) NOT NULL,
        date DATETIME NOT NULL,
        full_text MEDIUMTEXT NOT NULL,
        url VARCHAR(1000) NOT NULL,
        company_id BIGINT NULL,
        UNIQUE KEY uq_news_url (url),
        INDEX idx_company_id (company_id),
        CONSTRAINT fk_news_company
          FOREIGN KEY (company_id) REFERENCES Companies(id)
          ON DELETE SET NULL
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4
      COLLATE=utf8mb4_unicode_ci;
    """

    create_sentiments_sql = """
    CREATE TABLE IF NOT EXISTS Sentiments (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        label VARCHAR(50) NOT NULL,
        prob_pos FLOAT NOT NULL,
        prob_neg FLOAT NOT NULL,
        prob_neu FLOAT NOT NULL,
        score FLOAT NOT NULL,
        date DATETIME NOT NULL,
        news_id BIGINT NOT NULL,
        UNIQUE KEY uq_sentiments_news (news_id),
        INDEX idx_news_id (news_id),
        CONSTRAINT fk_sentiments_news
          FOREIGN KEY (news_id) REFERENCES News(id)
          ON DELETE CASCADE
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4
      COLLATE=utf8mb4_unicode_ci;
    """

    with conn.cursor() as cur:
        cur.execute(create_companies_sql)
        cur.execute(create_news_sql)
        cur.execute(create_sentiments_sql)
    conn.commit()


# ================================
# 2. JSON 로드 + 날짜 파싱
# ================================
def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("articles", []), data.get("groups", [])


def parse_article_datetime(article) -> datetime:
    """
    Naver API pubDate / published_at 등을 DATETIME으로 변환.
    못 읽으면 그냥 지금 시간으로.
    """
    raw = (
        article.get("published_at")
        or article.get("pubDate")
        or article.get("date")
    )

    if not raw:
        return datetime.now()

    raw = str(raw).strip()

    # 자주 쓰이는 포맷 몇 개 시도
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %z",  # Thu, 28 Nov 2024 09:03:00 +0900
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            # DB에는 timezone 없는 DATETIME으로 저장
            return dt.replace(tzinfo=None)
        except ValueError:
            continue

    # 다 실패하면 그냥 지금 시간
    return datetime.now()


# ================================
# 3. Companies / News / Sentiments 저장
# ================================
def save_articles_to_erd(conn, articles):
    """
    ERD 구조에 맞춰 저장:
      - Companies(name)  : query 기준으로 upsert
      - News             : 기사 본문 / URL 저장 (URL UNIQUE)
      - Sentiments       : 감정 점수 저장 (news_id UNIQUE – 1기사 1행)
    """
    news_sql = """
    INSERT INTO News (
        title, date, full_text, url, company_id
    ) VALUES (
        %(title)s, %(date)s, %(full_text)s, %(url)s, %(company_id)s
    )
    ON DUPLICATE KEY UPDATE
        title      = VALUES(title),
        date       = VALUES(date),
        full_text  = VALUES(full_text),
        company_id = VALUES(company_id),
        id         = LAST_INSERT_ID(id);  -- 기존 행이어도 lastrowid에 id 들어오게
    """

    sentiments_sql = """
    INSERT INTO Sentiments (
        label, prob_pos, prob_neg, prob_neu, score, date, news_id
    ) VALUES (
        %(label)s, %(prob_pos)s, %(prob_neg)s, %(prob_neu)s,
        %(score)s, %(date)s, %(news_id)s
    )
    ON DUPLICATE KEY UPDATE
        label    = VALUES(label),
        prob_pos = VALUES(prob_pos),
        prob_neg = VALUES(prob_neg),
        prob_neu = VALUES(prob_neu),
        score    = VALUES(score),
        date     = VALUES(date),
        id       = LAST_INSERT_ID(id);
    """

    with conn.cursor() as cur:
        for a in articles:
            # 1) 회사 이름(= query) → Companies 테이블에 upsert
            company_name = (a.get("query") or "").strip()
            company_id = None

            if company_name:
                # 이미 있는지 확인
                cur.execute(
                    "SELECT id FROM Companies WHERE name = %s",
                    (company_name,),
                )
                row = cur.fetchone()
                if row:
                    company_id = row["id"]
                else:
                    # 없으면 새로 INSERT
                    cur.execute(
                        "INSERT INTO Companies (name, sector_id) VALUES (%s, %s)",
                        (company_name, None),
                    )
                    company_id = cur.lastrowid

            # 2) 기사 날짜 / 제목 / 본문 / URL 준비
            article_dt = parse_article_datetime(a)

            title = (a.get("title") or "").strip()
            if len(title) > 500:
                title = title[:500]

            url = (a.get("url") or "").strip()
            if len(url) > 1000:
                url = url[:1000]

            news_params = {
                "title": title,
                "date": article_dt,
                "full_text": a.get("content") or "",
                "url": url,
                "company_id": company_id,
            }

            # 3) News upsert (URL 기준)
            cur.execute(news_sql, news_params)
            news_id = cur.lastrowid  # 새로 insert든 update든 여기로 기사 PK 확보

            # 4) Sentiments upsert (news_id 기준 1행)
            sentiment_params = {
                "label": a.get("sentiment_label") or "",
                "prob_pos": a.get("sentiment_prob_positive") or 0.0,
                "prob_neg": a.get("sentiment_prob_negative") or 0.0,
                "prob_neu": a.get("sentiment_prob_neutral") or 0.0,
                "score": a.get("sentiment_index") or 0.0,  # 0~100 지표
                "date": article_dt,
                "news_id": news_id,
            }
            cur.execute(sentiments_sql, sentiment_params)

    conn.commit()
    print(f"✅ ERD 테이블 저장 완료 (처리 기사 수: {len(articles)})")


# ================================
# 4. main
# ================================
def main():
    articles, groups = load_json(INPUT_FILE)
    print(f"📥 JSON 로드 완료: articles={len(articles)}, groups={len(groups)}")

    conn = get_connection()
    try:
        ensure_tables(conn)
        save_articles_to_erd(conn, articles)
    finally:
        conn.close()

    print("🎉 DB 저장 전체 완료! (Companies / News / Sentiments)")


if __name__ == "__main__":
    main()
