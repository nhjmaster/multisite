from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from sqlalchemy import create_engine, text
from openai import OpenAI
import threading
import time
import datetime
import os
import html
import math

app = FastAPI()

# ---------------------------
# 환경 변수
# ---------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:1234@jkworld-db:5432/multisite")
BASE_URL = os.getenv("BASE_URL", "https://www.jkworld.xyz")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
engine = create_engine(DATABASE_URL)

# ---------------------------
# 공통 유틸
# ---------------------------
def clean_html(content: str) -> str:
    if not content:
        return ""
    content = content.replace("```html", "").replace("```", "")
    return content.strip()

def now_year() -> int:
    return datetime.datetime.now().year

def fmt_won(n: float) -> str:
    return f"{int(round(n)):,}"

def get_category(keyword: str) -> str:
    keyword = (keyword or "").lower()
    if "etf" in keyword or "재테크" in keyword or "주식" in keyword or "투자" in keyword or "voo" in keyword or "schd" in keyword:
        return "재테크"
    elif "대출" in keyword or "금리" in keyword or "신용" in keyword or "주담대" in keyword or "전세대출" in keyword:
        return "대출"
    elif "연봉" in keyword or "실수령" in keyword or "월급" in keyword:
        return "연봉"
    return "기타"

# ---------------------------
# 네이버형 제목 생성
# ---------------------------
def build_naver_title(keyword: str) -> str:
    k = keyword.strip()
    y = now_year()

    if "연봉" in k or "실수령" in k or "월급" in k:
        if any(n in k for n in ["3000", "4000", "5000", "6000", "7000", "8000", "9000", "1억"]):
            return f"{k} 얼마일까? ({y} 기준)"
        return f"[{y} 기준] {k} 총정리｜4대보험·세금 반영"

    if "대출" in k or "금리" in k or "주담대" in k or "전세대출" in k:
        if any(n in k for n in ["1억", "2억", "3억", "4억", "5억"]):
            return f"{k} 얼마 나올까? ({y} 기준)"
        return f"{k} 총정리 ({y})｜월 상환액·이자 바로 계산"

    if "etf" in k.lower() or "투자" in k or "재테크" in k or "voo" in k.lower() or "schd" in k.lower():
        if any(n in k for n in ["10년", "20년", "30년", "50만원", "100만원"]):
            return f"{k} 하면 얼마 될까? ({y})"
        return f"{k} 추천/정리 ({y})｜초보도 이해하기 쉽게"

    return f"[{y} 최신] {k} 총정리"

def build_title(keyword: str) -> str:
    return build_naver_title(keyword)

# ---------------------------
# 키워드 기반 이미지
# ---------------------------
def get_smart_image(keyword: str):
    keyword = (keyword or "").lower()

    if "연봉" in keyword or "실수령" in keyword or "월급" in keyword:
        return "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=1200&q=80"
    elif "대출" in keyword or "금리" in keyword or "주담대" in keyword or "전세대출" in keyword:
        return "https://images.unsplash.com/photo-1554224154-26032ffc0d07?auto=format&fit=crop&w=1200&q=80"
    elif "etf" in keyword or "투자" in keyword or "주식" in keyword or "재테크" in keyword:
        return "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1200&q=80"

    return "https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?auto=format&fit=crop&w=1200&q=80"

def get_thumbnail(keyword: str, post_id: int) -> str:
    return get_smart_image(keyword)

# ---------------------------
# 본문 이미지 삽입
# ---------------------------
def insert_images(content: str, keyword: str) -> str:
    img = get_smart_image(keyword)
    alt = html.escape(keyword)

    hero = f'''
    <p>
        <img src="{img}" alt="{alt}" style="width:100%;border-radius:16px;margin:10px 0 24px;">
    </p>
    '''

    parts = content.split("</p>")

    if len(parts) > 3:
        parts.insert(2, f'''
        <p>
            <img src="{img}" alt="{alt}" style="width:100%;border-radius:16px;margin:20px 0;">
        </p>
        ''')

    if len(parts) > 7:
        parts.insert(6, f'''
        <p>
            <img src="{img}" alt="{alt}" style="width:100%;border-radius:16px;margin:20px 0;">
        </p>
        ''')

    return hero + "</p>".join(parts)

# ---------------------------
# 광고 삽입
# ---------------------------
def insert_ads(content: str) -> str:
    parts = content.split("</p>")
    if len(parts) > 4:
        parts.insert(2, '<div style="margin:28px 0;padding:16px;border:1px dashed #ccc;text-align:center;background:#fafafa;border-radius:12px;">[광고 영역]</div>')
        parts.insert(6, '<div style="margin:28px 0;padding:16px;border:1px dashed #ccc;text-align:center;background:#fafafa;border-radius:12px;">[광고 영역]</div>')
    return "</p>".join(parts)

# ---------------------------
# 계산기 CTA 삽입
# ---------------------------
def insert_cta_blocks(content: str, keyword: str) -> str:
    cta = ""

    if "연봉" in keyword or "실수령" in keyword or "월급" in keyword:
        cta = """
        <div style="margin:28px 0;padding:20px;background:#f0fff5;border:1px solid #d8f3df;border-radius:16px;">
            <h3 style="margin-top:0;">💰 연봉 실수령액 바로 계산하기</h3>
            <p>글로 보는 것보다 내 조건으로 계산하는 게 더 정확합니다.</p>
            <a href="/salary" style="display:inline-block;padding:12px 18px;background:#03c75a;color:white;border-radius:10px;font-weight:bold;">
                👉 연봉 계산기 바로가기
            </a>
        </div>
        """
    elif "대출" in keyword or "금리" in keyword or "주담대" in keyword or "전세대출" in keyword:
        cta = """
        <div style="margin:28px 0;padding:20px;background:#f0fdfa;border:1px solid #ccfbf1;border-radius:16px;">
            <h3 style="margin-top:0;">🏦 대출 이자 바로 계산하기</h3>
            <p>내 대출 조건으로 월 상환액과 총 이자를 바로 확인해보세요.</p>
            <a href="/loan" style="display:inline-block;padding:12px 18px;background:#0f766e;color:white;border-radius:10px;font-weight:bold;">
                👉 대출 계산기 바로가기
            </a>
        </div>
        """
    elif "etf" in keyword.lower() or "투자" in keyword or "재테크" in keyword or "voo" in keyword.lower() or "schd" in keyword.lower():
        cta = """
        <div style="margin:28px 0;padding:20px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:16px;">
            <h3 style="margin-top:0;">📈 ETF 수익 바로 계산하기</h3>
            <p>월 투자금과 기간을 넣고 예상 자산을 확인해보세요.</p>
            <a href="/etf" style="display:inline-block;padding:12px 18px;background:#2563eb;color:white;border-radius:10px;font-weight:bold;">
                👉 ETF 계산기 바로가기
            </a>
        </div>
        """

    parts = content.split("</p>")
    if len(parts) > 4 and cta:
        parts.insert(3, cta)

    return "</p>".join(parts)

# ---------------------------
# 관련 계산기/링크 추가
# ---------------------------
def add_related(content: str) -> str:
    return content + """
    <div style="margin-top:40px;padding:20px;background:#f0fff5;border-radius:16px;border:1px solid #d8f3df;">
        <h3 style="margin-top:0;">🧮 바로 계산해보기</h3>
        <p style="line-height:1.8;">
            연봉, 대출, ETF 수익까지 바로 계산해보세요.
        </p>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;">
            <a href="/salary" style="display:inline-block;padding:12px 18px;background:#03c75a;color:white;border-radius:10px;font-weight:bold;">
                연봉 계산기
            </a>
            <a href="/loan" style="display:inline-block;padding:12px 18px;background:#0f766e;color:white;border-radius:10px;font-weight:bold;">
                대출 계산기
            </a>
            <a href="/etf" style="display:inline-block;padding:12px 18px;background:#2563eb;color:white;border-radius:10px;font-weight:bold;">
                ETF 계산기
            </a>
        </div>
    </div>

    <div style="margin-top:40px;padding:20px;background:#fafafa;border-radius:16px;">
        <h3 style="margin-top:0;">📌 같이 보면 좋은 글</h3>
        <ul style="line-height:1.8;">
            <li><a href="/">최신 글 더 보기</a></li>
        </ul>
    </div>
    """

# ---------------------------
# 연봉 계산기 유틸
# ---------------------------
def calculate_salary_details(annual_salary: int):
    if annual_salary <= 0:
        return None

    monthly_gross = annual_salary / 12

    national_pension = monthly_gross * 0.045
    health_insurance = monthly_gross * 0.03545
    long_term_care = health_insurance * 0.1295
    employment_insurance = monthly_gross * 0.009

    total_insurance = (
        national_pension +
        health_insurance +
        long_term_care +
        employment_insurance
    )

    annual_taxable = annual_salary - (total_insurance * 12)

    if annual_taxable <= 14000000:
        annual_income_tax = annual_taxable * 0.06
    elif annual_taxable <= 50000000:
        annual_income_tax = (14000000 * 0.06) + ((annual_taxable - 14000000) * 0.15)
    elif annual_taxable <= 88000000:
        annual_income_tax = (14000000 * 0.06) + ((50000000 - 14000000) * 0.15) + ((annual_taxable - 50000000) * 0.24)
    elif annual_taxable <= 150000000:
        annual_income_tax = (
            (14000000 * 0.06) +
            ((50000000 - 14000000) * 0.15) +
            ((88000000 - 50000000) * 0.24) +
            ((annual_taxable - 88000000) * 0.35)
        )
    else:
        annual_income_tax = (
            (14000000 * 0.06) +
            ((50000000 - 14000000) * 0.15) +
            ((88000000 - 50000000) * 0.24) +
            ((150000000 - 88000000) * 0.35) +
            ((annual_taxable - 150000000) * 0.38)
        )

    monthly_income_tax = annual_income_tax / 12
    local_income_tax = monthly_income_tax * 0.1

    monthly_net = monthly_gross - total_insurance - monthly_income_tax - local_income_tax
    annual_net = monthly_net * 12

    return {
        "annual_salary": int(round(annual_salary)),
        "monthly_gross": int(round(monthly_gross)),
        "national_pension": int(round(national_pension)),
        "health_insurance": int(round(health_insurance)),
        "long_term_care": int(round(long_term_care)),
        "employment_insurance": int(round(employment_insurance)),
        "income_tax": int(round(monthly_income_tax)),
        "local_income_tax": int(round(local_income_tax)),
        "monthly_net": int(round(monthly_net)),
        "annual_net": int(round(annual_net)),
    }

# ---------------------------
# 대출 계산기 유틸
# ---------------------------
def calculate_loan_payment(principal: float, annual_rate: float, years: int):
    if principal <= 0 or annual_rate < 0 or years <= 0:
        return None

    monthly_rate = annual_rate / 100 / 12
    months = years * 12

    if monthly_rate == 0:
        monthly_payment = principal / months
    else:
        monthly_payment = principal * (monthly_rate * (1 + monthly_rate) ** months) / ((1 + monthly_rate) ** months - 1)

    total_payment = monthly_payment * months
    total_interest = total_payment - principal

    return {
        "monthly_payment": int(round(monthly_payment)),
        "total_payment": int(round(total_payment)),
        "total_interest": int(round(total_interest)),
        "months": months
    }

# ---------------------------
# ETF 계산기 유틸
# ---------------------------
def calculate_etf(monthly_invest: float, annual_return: float, years: int):
    if monthly_invest <= 0 or years <= 0:
        return None

    monthly_rate = annual_return / 100 / 12
    months = years * 12

    future_value = 0
    for _ in range(months):
        future_value = (future_value + monthly_invest) * (1 + monthly_rate)

    total_invested = monthly_invest * months
    profit = future_value - total_invested

    return {
        "total_invested": int(round(total_invested)),
        "future_value": int(round(future_value)),
        "profit": int(round(profit)),
        "months": months
    }

# ---------------------------
# 레이아웃
# ---------------------------
def layout(content: str, page_title: str = "JK World") -> str:
    return f"""
    <!doctype html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{html.escape(page_title)}</title>
        <meta name="description" content="재테크, 연봉, 대출 정보를 정리하는 블로그">
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f5f6f7;
                color: #222;
            }}
            .header {{
                background: #03c75a;
                color: white;
                padding: 18px 20px;
                font-size: 22px;
                font-weight: bold;
            }}
            .header a {{
                color: white;
                text-decoration: none;
            }}
            .container {{
                max-width: 1180px;
                margin: 24px auto;
                padding: 0 16px;
            }}
            .tabs {{
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
                margin-bottom: 24px;
            }}
            .tab {{
                padding: 10px 18px;
                border-radius: 999px;
                background: #fff;
                border: 1px solid #e4e6eb;
                color: #333;
                text-decoration: none;
                font-size: 14px;
                transition: all .2s ease;
            }}
            .tab:hover {{
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.06);
            }}
            .tab.active {{
                background: #03c75a;
                color: #fff;
                border-color: #03c75a;
                font-weight: bold;
            }}
            .section-title {{
                margin: 0 0 12px 0;
                font-size: 22px;
            }}
            .hot-box {{
                background: #fff;
                border-radius: 18px;
                padding: 20px;
                margin-bottom: 24px;
                box-shadow: 0 6px 20px rgba(0,0,0,0.04);
            }}
            .hot-box ul {{
                margin: 0;
                padding-left: 18px;
                line-height: 1.9;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 22px;
            }}
            .card {{
                background: #fff;
                border-radius: 18px;
                overflow: hidden;
                box-shadow: 0 8px 24px rgba(0,0,0,0.05);
                transition: transform .18s ease;
            }}
            .card:hover {{
                transform: translateY(-4px);
            }}
            .thumb {{
                width: 100%;
                height: 190px;
                object-fit: cover;
                display: block;
            }}
            .card-body {{
                padding: 16px;
            }}
            .card-title {{
                font-size: 18px;
                font-weight: bold;
                line-height: 1.5;
                margin-bottom: 8px;
            }}
            .card-meta {{
                font-size: 13px;
                color: #666;
            }}
            .pagination {{
                text-align: center;
                margin: 36px 0 12px;
            }}
            .pagination a, .pagination b {{
                display: inline-block;
                margin: 0 6px;
                padding: 8px 12px;
                border-radius: 10px;
                background: #fff;
                border: 1px solid #e4e6eb;
                text-decoration: none;
                color: #333;
            }}
            .pagination b {{
                background: #03c75a;
                color: white;
                border-color: #03c75a;
            }}
            .post-wrap {{
                background: #fff;
                border-radius: 22px;
                padding: 28px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.05);
            }}
            .post-wrap img {{
                width: 100%;
                border-radius: 18px;
                margin: 20px 0 28px;
            }}
            .post-wrap h1 {{
                font-size: 34px;
                line-height: 1.35;
                margin-bottom: 10px;
            }}
            .post-wrap p {{
                line-height: 1.9;
                font-size: 17px;
                color: #2a2a2a;
            }}
            .admin-box {{
                background: #fff;
                border-radius: 18px;
                padding: 20px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.05);
            }}
            input, textarea, select {{
                width: 100%;
                padding: 12px;
                margin: 8px 0 16px;
                border: 1px solid #ddd;
                border-radius: 12px;
                font-size: 15px;
            }}
            button {{
                background: #03c75a;
                color: #fff;
                border: none;
                padding: 12px 18px;
                border-radius: 12px;
                font-size: 15px;
                cursor: pointer;
            }}
            a {{
                color: inherit;
                text-decoration: none;
            }}
            table {{
                width: 100%;
            }}
            .calc-grid {{
                display:grid;
                grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
                gap:14px;
                margin-top:20px;
            }}
            .calc-card {{
                padding:18px;
                background:#f7f8fa;
                border-radius:16px;
            }}
            @media (max-width: 768px) {{
                .post-wrap {{
                    padding: 20px;
                }}
                .post-wrap h1 {{
                    font-size: 28px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <a href="/">🌿 JK World</a>
        </div>
        <div class="container">
            {content}
        </div>
    </body>
    </html>
    """

# ---------------------------
# DB 헬퍼
# ---------------------------
def keyword_exists(keyword: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT 1 FROM posts WHERE keyword=:k LIMIT 1"), {"k": keyword}).fetchone()
        return row is not None

def safe_insert_post(keyword: str, title: str, content: str, category: str):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO posts(keyword, title, content, views, category, created_at)
            VALUES(:k, :t, :c, 0, :cat, NOW())
        """), {
            "k": keyword,
            "t": title,
            "c": content,
            "cat": category
        })
        conn.commit()

# ---------------------------
# GPT 글 생성 (네이버 최적화 버전)
# ---------------------------
def generate_post(keyword: str):
    if not client:
        print("OPENAI_API_KEY 없음 - 글 생성 스킵")
        return

    keyword = keyword.strip()
    if not keyword or keyword_exists(keyword):
        return

    category = get_category(keyword)
    title = build_naver_title(keyword)

    prompt = f"""
아래 키워드로 네이버 블로그 상위노출 스타일의 글을 작성하세요.

키워드: {keyword}
제목 참고: {title}

조건:

[전체 스타일]
- 한국어
- 사람이 직접 쓴 것처럼 자연스럽게
- 너무 딱딱하지 않게
- 모바일에서 읽기 쉽게 짧은 문장 위주
- 길이는 1200~1800자
- 초보자도 이해 가능하게 쉽게 설명

[제목 스타일]
- 네이버 블로그에서 클릭 잘 나오는 스타일
- "총정리", "최신", "기준", "얼마일까?", "체크리스트", "바로 계산" 같은 표현 선호

[구조 반드시 지킬 것]
1. 도입: 독자가 바로 궁금해할 질문/문제 제기
2. 핵심 요약: 결론 먼저
3. 상세 설명: 쉽게 풀어서 설명
4. 리스트 또는 표 형태 요약
5. 계산기 유도 문장 포함
6. 마무리

[반드시 포함할 문장]
- "정확한 금액은 아래 계산기로 직접 확인해보세요."
- "헷갈리는 부분은 표로 먼저 보는 것이 가장 빠릅니다."

[HTML 규칙]
- 반드시 HTML로 작성
- <h2>, <h3>, <p>, <ul>, <li>, <table>, <tr>, <td> 적극 사용
- 제목(<h1>)은 넣지 말 것
- 문단은 짧게 나눌 것

[중요]
- 검색 의도가 강한 정보성 글처럼 작성
- 광고성/홍보성 문장 금지
- 말투는 블로그 후기+정보글 중간 느낌
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        content = clean_html(res.choices[0].message.content)

        content = insert_images(content, keyword)
        content = insert_cta_blocks(content, keyword)
        content = insert_ads(content)
        content = add_related(content)

        safe_insert_post(keyword, title, content, category)
        print(f"생성 완료: {keyword}")

    except Exception as e:
        print("generate_post 에러:", e)

# ---------------------------
# AI Agent
# ---------------------------
def seed_keywords():
    y = now_year()
    return [
        f"연봉 3000 실수령 {y}",
        f"연봉 5000 실수령 {y}",
        f"연봉 7000 실수령 {y}",
        f"연봉 1억 실수령 {y}",
        f"대출 3억 이자 계산 {y}",
        f"주담대 5억 월 상환액 {y}",
        f"ETF 적립식 투자 방법 {y}",
        f"월 50만원 ETF 투자 {y}",
        f"VOO 적립식 투자 {y}",
        f"SCHD 투자 방법 {y}",
    ]

def expand_popular():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT keyword FROM posts
            ORDER BY views DESC, id DESC
            LIMIT 5
        """))
        keywords = [r[0] for r in rows if r[0]]

    for k in keywords:
        candidate = f"{k} 총정리"
        if not keyword_exists(candidate):
            generate_post(candidate)
            time.sleep(3)

def improve_low_posts():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, keyword, views FROM posts
            WHERE views < 3
            ORDER BY id DESC
            LIMIT 5
        """))
        targets = [dict(r._mapping) for r in rows]

    for p in targets:
        better_title = build_naver_title(f"{p['keyword']}")
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE posts
                SET title=:t
                WHERE id=:id
            """), {"t": better_title, "id": p["id"]})
            conn.commit()

def ensure_seed_posts():
    for k in seed_keywords():
        if not keyword_exists(k):
            generate_post(k)
            time.sleep(3)

def money_agent():
    while True:
        try:
            print("🤖 AI Agent 실행")
            ensure_seed_posts()
            expand_popular()
            improve_low_posts()
            time.sleep(60 * 60)
        except Exception as e:
            print("money_agent 에러:", e)
            time.sleep(60)

# ---------------------------
# 홈
# ---------------------------
@app.get("/", response_class=HTMLResponse)
def home(page: int = Query(1), category: str = Query("전체")):
    limit = 9
    offset = (page - 1) * limit

    with engine.connect() as conn:
        cats = conn.execute(text("SELECT DISTINCT category FROM posts ORDER BY category"))
        categories = ["전체"] + [c[0] for c in cats if c[0]]

        if category == "전체":
            total = conn.execute(text("SELECT COUNT(*) FROM posts")).scalar() or 0
            rows = conn.execute(text("""
                SELECT * FROM posts
                ORDER BY id DESC
                LIMIT :limit OFFSET :offset
            """), {"limit": limit, "offset": offset})
            hot = conn.execute(text("""
                SELECT * FROM posts
                ORDER BY views DESC, id DESC
                LIMIT 5
            """))
        else:
            total = conn.execute(text("""
                SELECT COUNT(*) FROM posts
                WHERE category=:cat OR category IS NULL
            """), {"cat": category}).scalar() or 0

            rows = conn.execute(text("""
                SELECT * FROM posts
                WHERE category=:cat OR category IS NULL
                ORDER BY id DESC
                LIMIT :limit OFFSET :offset
            """), {"cat": category, "limit": limit, "offset": offset})

            hot = conn.execute(text("""
                SELECT * FROM posts
                WHERE category=:cat OR category IS NULL
                ORDER BY views DESC, id DESC
                LIMIT 5
            """), {"cat": category})

        posts = [dict(r._mapping) for r in rows]
        hot_posts = [dict(r._mapping) for r in hot]

    total_pages = max(1, (total + limit - 1) // limit)

    content = """
    <div class="hot-box" style="background:linear-gradient(135deg,#03c75a,#17b75e);color:white;">
        <h2 class="section-title" style="color:white;">🧮 실전 계산기 모음</h2>
        <p style="margin:0 0 14px 0;line-height:1.8;">
            연봉, 대출, ETF 수익까지 바로 계산해보세요.
        </p>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <a href="/salary" style="display:inline-block;padding:12px 18px;background:white;color:#03c75a;border-radius:12px;font-weight:bold;">연봉 계산기</a>
            <a href="/loan" style="display:inline-block;padding:12px 18px;background:white;color:#0f766e;border-radius:12px;font-weight:bold;">대출 계산기</a>
            <a href="/etf" style="display:inline-block;padding:12px 18px;background:white;color:#2563eb;border-radius:12px;font-weight:bold;">ETF 계산기</a>
        </div>
    </div>
    """

    content += '<div class="tabs">'
    for c in categories:
        cls = "tab active" if c == category else "tab"
        content += f'<a href="/?category={c}" class="{cls}">{c}</a>'
    content += '</div>'

    content += '<div class="hot-box">'
    content += '<h2 class="section-title">🔥 인기글</h2><ul>'
    for p in hot_posts:
        content += f'<li><a href="/post/{p["id"]}">{html.escape(p["title"] or "제목 없음")}</a> (조회수 {p["views"]})</li>'
    content += '</ul></div>'

    content += '<div class="grid">'
    for p in posts:
        img = get_thumbnail(p.get("keyword", "blog"), p["id"])
        title = html.escape(p.get("title") or "제목 없음")
        views = p.get("views", 0)
        cat = html.escape(p.get("category") or "기타")

        content += f"""
        <div class="card">
            <a href="/post/{p['id']}">
                <img class="thumb" src="{img}" alt="{title}">
                <div class="card-body">
                    <div class="card-title">{title}</div>
                    <div class="card-meta">{cat} · 조회수 {views}</div>
                </div>
            </a>
        </div>
        """
    content += "</div>"

    content += '<div class="pagination">'
    if page > 1:
        content += f'<a href="/?category={category}&page={page-1}">◀ 이전</a>'

    for i in range(1, total_pages + 1):
        if i == page:
            content += f'<b>{i}</b>'
        else:
            content += f'<a href="/?category={category}&page={i}">{i}</a>'

    if page < total_pages:
        content += f'<a href="/?category={category}&page={page+1}">다음 ▶</a>'
    content += '</div>'

    return layout(content, "JK World")

# ---------------------------
# 연봉 계산기
# ---------------------------
@app.get("/salary", response_class=HTMLResponse)
def salary_calculator():
    content = """
    <div class="post-wrap">
        <a href="/" style="display:inline-block;margin-bottom:16px;color:#03c75a;font-weight:bold;">← 홈으로</a>
        <h1>💰 연봉 실수령액 계산기</h1>
        <p>국민연금, 건강보험, 장기요양보험, 고용보험, 소득세, 지방소득세를 반영한 예상 월 실수령액을 계산합니다.</p>

        <div style="margin-top:24px;padding:24px;background:#fafafa;border-radius:18px;">
            <label>연봉 입력 (세전)</label>
            <input id="salary" type="number" placeholder="예: 50000000">
            <button onclick="calcSalary()" style="margin-top:12px;">계산하기</button>
        </div>

        <div id="salary-result" style="margin-top:28px;"></div>

        <script>
        async function calcSalary() {
            const salary = document.getElementById("salary").value;
            if (!salary || Number(salary) <= 0) {
                alert("연봉을 올바르게 입력해주세요.");
                return;
            }

            const res = await fetch("/salary/calc", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ salary: salary })
            });

            const data = await res.json();

            if (data.error) {
                document.getElementById("salary-result").innerHTML = `<div style="padding:18px;background:#fff0f0;border-radius:14px;color:#d93025;">${data.error}</div>`;
                return;
            }

            document.getElementById("salary-result").innerHTML = `
                <div style="background:#fff;border-radius:22px;padding:28px;box-shadow:0 8px 24px rgba(0,0,0,0.05);">
                    <h2>📊 계산 결과</h2>
                    <div class="calc-grid">
                        <div class="calc-card"><div>세전 월급</div><div style="font-size:24px;font-weight:bold;margin-top:8px;">${data.monthly_gross}원</div></div>
                        <div class="calc-card" style="background:#f0fff5;"><div>월 실수령액</div><div style="font-size:28px;font-weight:bold;margin-top:8px;color:#03c75a;">${data.monthly_net}원</div></div>
                    </div>

                    <div style="margin-top:28px;">
                        <h3>🧾 월 공제 상세</h3>
                        <table style="width:100%;border-collapse:collapse;margin-top:12px;">
                            <tr><td style="padding:12px;border-bottom:1px solid #eee;">국민연금</td><td style="padding:12px;border-bottom:1px solid #eee;text-align:right;">${data.national_pension}원</td></tr>
                            <tr><td style="padding:12px;border-bottom:1px solid #eee;">건강보험</td><td style="padding:12px;border-bottom:1px solid #eee;text-align:right;">${data.health_insurance}원</td></tr>
                            <tr><td style="padding:12px;border-bottom:1px solid #eee;">장기요양보험</td><td style="padding:12px;border-bottom:1px solid #eee;text-align:right;">${data.long_term_care}원</td></tr>
                            <tr><td style="padding:12px;border-bottom:1px solid #eee;">고용보험</td><td style="padding:12px;border-bottom:1px solid #eee;text-align:right;">${data.employment_insurance}원</td></tr>
                            <tr><td style="padding:12px;border-bottom:1px solid #eee;">소득세</td><td style="padding:12px;border-bottom:1px solid #eee;text-align:right;">${data.income_tax}원</td></tr>
                            <tr><td style="padding:12px;border-bottom:1px solid #eee;">지방소득세</td><td style="padding:12px;border-bottom:1px solid #eee;text-align:right;">${data.local_income_tax}원</td></tr>
                            <tr><td style="padding:14px;font-weight:bold;">총 공제액</td><td style="padding:14px;text-align:right;font-weight:bold;">${data.total_deduction}원</td></tr>
                        </table>
                    </div>

                    <div style="margin-top:28px;padding:18px;background:#fafafa;border-radius:16px;">
                        <div>예상 연 실수령액</div>
                        <div style="font-size:26px;font-weight:bold;margin-top:8px;">${data.annual_net}원</div>
                    </div>
                </div>
            `;
        }
        </script>
    </div>
    """
    return layout(content, "연봉 실수령액 계산기")

@app.post("/salary/calc")
async def salary_calc(request: Request):
    try:
        data = await request.json()
        annual_salary = int(str(data.get("salary", "0")).replace(",", "").strip())

        if annual_salary <= 0:
            return JSONResponse({"error": "연봉을 올바르게 입력해주세요."})

        result = calculate_salary_details(annual_salary)
        total_deduction = (
            result["national_pension"] +
            result["health_insurance"] +
            result["long_term_care"] +
            result["employment_insurance"] +
            result["income_tax"] +
            result["local_income_tax"]
        )

        return JSONResponse({
            "monthly_gross": fmt_won(result["monthly_gross"]),
            "national_pension": fmt_won(result["national_pension"]),
            "health_insurance": fmt_won(result["health_insurance"]),
            "long_term_care": fmt_won(result["long_term_care"]),
            "employment_insurance": fmt_won(result["employment_insurance"]),
            "income_tax": fmt_won(result["income_tax"]),
            "local_income_tax": fmt_won(result["local_income_tax"]),
            "total_deduction": fmt_won(total_deduction),
            "monthly_net": fmt_won(result["monthly_net"]),
            "annual_net": fmt_won(result["annual_net"]),
        })
    except Exception as e:
        return JSONResponse({"error": f"입력 오류: {str(e)}"})

# ---------------------------
# 대출 계산기
# ---------------------------
@app.get("/loan", response_class=HTMLResponse)
def loan_calculator():
    content = """
    <div class="post-wrap">
        <a href="/" style="display:inline-block;margin-bottom:16px;color:#0f766e;font-weight:bold;">← 홈으로</a>
        <h1>🏦 대출 이자 계산기</h1>
        <p>대출 원금, 금리, 기간을 입력하면 예상 월 상환액과 총 이자를 계산합니다.</p>

        <div style="margin-top:24px;padding:24px;background:#fafafa;border-radius:18px;">
            <label>대출 원금</label>
            <input id="loan-principal" type="number" placeholder="예: 300000000">

            <label>연이율 (%)</label>
            <input id="loan-rate" type="number" step="0.01" placeholder="예: 4.2">

            <label>기간 (년)</label>
            <input id="loan-years" type="number" placeholder="예: 30">

            <button onclick="calcLoan()" style="margin-top:12px;background:#0f766e;">계산하기</button>
        </div>

        <div id="loan-result" style="margin-top:28px;"></div>

        <script>
        async function calcLoan() {
            const principal = document.getElementById("loan-principal").value;
            const rate = document.getElementById("loan-rate").value;
            const years = document.getElementById("loan-years").value;

            if (!principal || !rate || !years) {
                alert("모든 값을 입력해주세요.");
                return;
            }

            const res = await fetch("/loan/calc", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ principal, rate, years })
            });

            const data = await res.json();

            if (data.error) {
                document.getElementById("loan-result").innerHTML = `<div style="padding:18px;background:#fff0f0;border-radius:14px;color:#d93025;">${data.error}</div>`;
                return;
            }

            document.getElementById("loan-result").innerHTML = `
                <div style="background:#fff;border-radius:22px;padding:28px;box-shadow:0 8px 24px rgba(0,0,0,0.05);">
                    <h2>📊 계산 결과</h2>
                    <div class="calc-grid">
                        <div class="calc-card"><div>월 상환액</div><div style="font-size:28px;font-weight:bold;margin-top:8px;color:#0f766e;">${data.monthly_payment}원</div></div>
                        <div class="calc-card"><div>총 이자</div><div style="font-size:24px;font-weight:bold;margin-top:8px;">${data.total_interest}원</div></div>
                        <div class="calc-card"><div>총 상환액</div><div style="font-size:24px;font-weight:bold;margin-top:8px;">${data.total_payment}원</div></div>
                    </div>
                </div>
            `;
        }
        </script>
    </div>
    """
    return layout(content, "대출 이자 계산기")

@app.post("/loan/calc")
async def loan_calc(request: Request):
    try:
        data = await request.json()
        principal = float(str(data.get("principal", "0")).replace(",", "").strip())
        rate = float(str(data.get("rate", "0")).replace(",", "").strip())
        years = int(str(data.get("years", "0")).replace(",", "").strip())

        result = calculate_loan_payment(principal, rate, years)
        if not result:
            return JSONResponse({"error": "입력값을 확인해주세요."})

        return JSONResponse({
            "monthly_payment": fmt_won(result["monthly_payment"]),
            "total_interest": fmt_won(result["total_interest"]),
            "total_payment": fmt_won(result["total_payment"]),
        })
    except Exception as e:
        return JSONResponse({"error": f"입력 오류: {str(e)}"})

# ---------------------------
# ETF 계산기
# ---------------------------
@app.get("/etf", response_class=HTMLResponse)
def etf_calculator():
    content = """
    <div class="post-wrap">
        <a href="/" style="display:inline-block;margin-bottom:16px;color:#2563eb;font-weight:bold;">← 홈으로</a>
        <h1>📈 ETF 적립식 수익 계산기</h1>
        <p>매달 투자 금액, 기대 수익률, 투자 기간을 입력하면 예상 최종 자산을 계산합니다.</p>

        <div style="margin-top:24px;padding:24px;background:#fafafa;border-radius:18px;">
            <label>월 투자금</label>
            <input id="etf-monthly" type="number" placeholder="예: 500000">

            <label>연 수익률 (%)</label>
            <input id="etf-return" type="number" step="0.1" placeholder="예: 8">

            <label>투자 기간 (년)</label>
            <input id="etf-years" type="number" placeholder="예: 10">

            <button onclick="calcEtf()" style="margin-top:12px;background:#2563eb;">계산하기</button>
        </div>

        <div id="etf-result" style="margin-top:28px;"></div>

        <script>
        async function calcEtf() {
            const monthly = document.getElementById("etf-monthly").value;
            const rate = document.getElementById("etf-return").value;
            const years = document.getElementById("etf-years").value;

            if (!monthly || !rate || !years) {
                alert("모든 값을 입력해주세요.");
                return;
            }

            const res = await fetch("/etf/calc", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ monthly, rate, years })
            });

            const data = await res.json();

            if (data.error) {
                document.getElementById("etf-result").innerHTML = `<div style="padding:18px;background:#fff0f0;border-radius:14px;color:#d93025;">${data.error}</div>`;
                return;
            }

            document.getElementById("etf-result").innerHTML = `
                <div style="background:#fff;border-radius:22px;padding:28px;box-shadow:0 8px 24px rgba(0,0,0,0.05);">
                    <h2>📊 계산 결과</h2>
                    <div class="calc-grid">
                        <div class="calc-card"><div>총 투자 원금</div><div style="font-size:24px;font-weight:bold;margin-top:8px;">${data.total_invested}원</div></div>
                        <div class="calc-card" style="background:#eff6ff;"><div>예상 최종 자산</div><div style="font-size:28px;font-weight:bold;margin-top:8px;color:#2563eb;">${data.future_value}원</div></div>
                        <div class="calc-card"><div>예상 수익</div><div style="font-size:24px;font-weight:bold;margin-top:8px;">${data.profit}원</div></div>
                    </div>
                </div>
            `;
        }
        </script>
    </div>
    """
    return layout(content, "ETF 적립식 수익 계산기")

@app.post("/etf/calc")
async def etf_calc(request: Request):
    try:
        data = await request.json()
        monthly = float(str(data.get("monthly", "0")).replace(",", "").strip())
        rate = float(str(data.get("rate", "0")).replace(",", "").strip())
        years = int(str(data.get("years", "0")).replace(",", "").strip())

        result = calculate_etf(monthly, rate, years)
        if not result:
            return JSONResponse({"error": "입력값을 확인해주세요."})

        return JSONResponse({
            "total_invested": fmt_won(result["total_invested"]),
            "future_value": fmt_won(result["future_value"]),
            "profit": fmt_won(result["profit"]),
        })
    except Exception as e:
        return JSONResponse({"error": f"입력 오류: {str(e)}"})

# ---------------------------
# 상세
# ---------------------------
@app.get("/post/{id}", response_class=HTMLResponse)
def post_detail(id: int):
    with engine.connect() as conn:
        conn.execute(text("UPDATE posts SET views=views+1 WHERE id=:id"), {"id": id})
        conn.commit()
        row = conn.execute(text("SELECT * FROM posts WHERE id=:id"), {"id": id}).fetchone()

    if not row:
        return HTMLResponse(layout("<div class='post-wrap'><h1>글을 찾을 수 없습니다.</h1></div>", "Not Found"), status_code=404)

    r = dict(row._mapping)
    img = get_thumbnail(r.get("keyword", "blog"), r["id"])
    title = html.escape(r.get("title") or "제목 없음")

    content = f"""
    <div class="post-wrap">
        <a href="/" style="display:inline-block;margin-bottom:16px;color:#03c75a;font-weight:bold;">← 목록으로</a>
        <h1>{title}</h1>
        <div style="color:#666;font-size:14px;">조회수 {r.get("views", 0)} · 카테고리 {html.escape(r.get("category") or "기타")}</div>
        <img src="{img}" alt="{title}">
        {r.get("content") or ""}
    </div>
    """
    return layout(content, title)

# ---------------------------
# 관리자
# ---------------------------
@app.get("/jkadmin/posts", response_class=HTMLResponse)
def admin_posts():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM posts ORDER BY id DESC"))
        posts = [dict(r._mapping) for r in rows]

    content = """
    <div class="admin-box">
        <h1>관리자 - 글 관리</h1>
        <p><a href="/jkadmin/new" style="color:#03c75a;font-weight:bold;">+ 새 글 작성</a></p>
    """

    for p in posts:
        title = html.escape(p.get("title") or "제목 없음")
        content += f"""
        <div style="padding:14px 0;border-bottom:1px solid #eee;">
            <b>{title}</b> (조회수 {p.get('views', 0)})
            <div style="margin-top:8px;">
                <a href="/jkadmin/edit/{p['id']}" style="margin-right:12px;color:#03c75a;">수정</a>
                <a href="/jkadmin/delete/{p['id']}" style="color:#d93025;">삭제</a>
            </div>
        </div>
        """

    content += "</div>"
    return layout(content, "관리자")

@app.get("/jkadmin/new", response_class=HTMLResponse)
def admin_new_form():
    content = """
    <div class="admin-box">
        <h1>새 글 작성</h1>
        <form method="post">
            <label>키워드</label>
            <input name="keyword" placeholder="예: 직장인 ETF 추천">
            <label>제목</label>
            <input name="title" placeholder="제목 입력">
            <label>카테고리</label>
            <select name="category">
                <option value="재테크">재테크</option>
                <option value="대출">대출</option>
                <option value="연봉">연봉</option>
                <option value="기타">기타</option>
            </select>
            <label>내용 (HTML 가능)</label>
            <textarea name="content" rows="18"></textarea>
            <button type="submit">저장</button>
        </form>
    </div>
    """
    return layout(content, "새 글 작성")

@app.post("/jkadmin/new")
def admin_new_post(
    keyword: str = Form(...),
    title: str = Form(...),
    category: str = Form(...),
    content: str = Form(...)
):
    safe_insert_post(keyword.strip(), title.strip(), content.strip(), category.strip())
    return RedirectResponse("/jkadmin/posts", status_code=302)

@app.get("/jkadmin/edit/{id}", response_class=HTMLResponse)
def admin_edit_form(id: int):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM posts WHERE id=:id"), {"id": id}).fetchone()

    if not row:
        return RedirectResponse("/jkadmin/posts", status_code=302)

    r = dict(row._mapping)
    content = f"""
    <div class="admin-box">
        <h1>글 수정</h1>
        <form method="post">
            <label>키워드</label>
            <input name="keyword" value="{html.escape(r.get('keyword') or '')}">
            <label>제목</label>
            <input name="title" value="{html.escape(r.get('title') or '')}">
            <label>카테고리</label>
            <input name="category" value="{html.escape(r.get('category') or '기타')}">
            <label>내용</label>
            <textarea name="content" rows="18">{html.escape(r.get('content') or '')}</textarea>
            <button type="submit">수정 저장</button>
        </form>
    </div>
    """
    return layout(content, "글 수정")

@app.post("/jkadmin/edit/{id}")
def admin_edit_post(
    id: int,
    keyword: str = Form(...),
    title: str = Form(...),
    category: str = Form(...),
    content: str = Form(...)
):
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE posts
            SET keyword=:k, title=:t, category=:cat, content=:c
            WHERE id=:id
        """), {
            "k": keyword.strip(),
            "t": title.strip(),
            "cat": category.strip(),
            "c": content,
            "id": id
        })
        conn.commit()

    return RedirectResponse("/jkadmin/posts", status_code=302)

@app.get("/jkadmin/delete/{id}")
def admin_delete_post(id: int):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM posts WHERE id=:id"), {"id": id})
        conn.commit()
    return RedirectResponse("/jkadmin/posts", status_code=302)

# ---------------------------
# robots / sitemap / ads
# ---------------------------
@app.get("/robots.txt")
def robots():
    robots_txt = f"""User-agent: *
Allow: /
Sitemap: {BASE_URL}/sitemap.xml
"""
    return Response(content=robots_txt, media_type="text/plain")

@app.get("/sitemap.xml")
def sitemap():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id FROM posts ORDER BY id DESC"))
        urls = "".join([f"<url><loc>{BASE_URL}/post/{r[0]}</loc></url>" for r in rows])

    urls += f"<url><loc>{BASE_URL}/salary</loc></url>"
    urls += f"<url><loc>{BASE_URL}/loan</loc></url>"
    urls += f"<url><loc>{BASE_URL}/etf</loc></url>"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
"""
    return Response(content=xml, media_type="application/xml")

@app.get("/ads.txt")
def ads_txt():
    ads_content = """google.com, pub-1484829825999769, DIRECT, f08c47fec0942fa0"""
    return Response(content=ads_content, media_type="text/plain")

# ---------------------------
# 앱 시작 시 AI Agent 실행
# ---------------------------
threading.Thread(target=money_agent, daemon=True).start()