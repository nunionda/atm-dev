"""
Korean Stock Ticker Dictionary
Maps stock codes to their market suffix (.KS for KOSPI, .KQ for KOSDAQ) and names.
"""
from __future__ import annotations

KOREAN_TICKERS = [
    # === KOSPI (.KS) ===
    {"code": "005930", "market": "KS", "name_kr": "삼성전자", "name_en": "Samsung Electronics"},
    {"code": "000660", "market": "KS", "name_kr": "SK하이닉스", "name_en": "SK Hynix"},
    {"code": "005380", "market": "KS", "name_kr": "현대자동차", "name_en": "Hyundai Motor"},
    {"code": "000270", "market": "KS", "name_kr": "기아", "name_en": "Kia"},
    {"code": "005490", "market": "KS", "name_kr": "POSCO홀딩스", "name_en": "POSCO Holdings"},
    {"code": "035420", "market": "KS", "name_kr": "네이버", "name_en": "Naver"},
    {"code": "051910", "market": "KS", "name_kr": "LG화학", "name_en": "LG Chem"},
    {"code": "006400", "market": "KS", "name_kr": "삼성SDI", "name_en": "Samsung SDI"},
    {"code": "003670", "market": "KS", "name_kr": "포스코퓨처엠", "name_en": "POSCO Future M"},
    {"code": "105560", "market": "KS", "name_kr": "KB금융", "name_en": "KB Financial Group"},
    {"code": "055550", "market": "KS", "name_kr": "신한지주", "name_en": "Shinhan Financial"},
    {"code": "086790", "market": "KS", "name_kr": "하나금융지주", "name_en": "Hana Financial Group"},
    {"code": "012330", "market": "KS", "name_kr": "현대모비스", "name_en": "Hyundai Mobis"},
    {"code": "066570", "market": "KS", "name_kr": "LG전자", "name_en": "LG Electronics"},
    {"code": "034730", "market": "KS", "name_kr": "SK", "name_en": "SK Inc"},
    {"code": "003550", "market": "KS", "name_kr": "LG", "name_en": "LG Corp"},
    {"code": "032830", "market": "KS", "name_kr": "삼성생명", "name_en": "Samsung Life Insurance"},
    {"code": "009150", "market": "KS", "name_kr": "삼성전기", "name_en": "Samsung Electro-Mechanics"},
    {"code": "010130", "market": "KS", "name_kr": "고려아연", "name_en": "Korea Zinc"},
    {"code": "030200", "market": "KS", "name_kr": "KT", "name_en": "KT Corp"},
    {"code": "017670", "market": "KS", "name_kr": "SK텔레콤", "name_en": "SK Telecom"},
    {"code": "033780", "market": "KS", "name_kr": "KT&G", "name_en": "KT&G"},
    {"code": "096770", "market": "KS", "name_kr": "SK이노베이션", "name_en": "SK Innovation"},
    {"code": "011200", "market": "KS", "name_kr": "HMM", "name_en": "HMM"},
    {"code": "034020", "market": "KS", "name_kr": "두산에너빌리티", "name_en": "Doosan Enerbility"},
    {"code": "000810", "market": "KS", "name_kr": "삼성화재", "name_en": "Samsung Fire & Marine"},
    {"code": "028260", "market": "KS", "name_kr": "삼성물산", "name_en": "Samsung C&T"},
    {"code": "018260", "market": "KS", "name_kr": "삼성에스디에스", "name_en": "Samsung SDS"},
    {"code": "010950", "market": "KS", "name_kr": "S-Oil", "name_en": "S-Oil"},
    {"code": "316140", "market": "KS", "name_kr": "우리금융지주", "name_en": "Woori Financial Group"},
    {"code": "352820", "market": "KS", "name_kr": "하이브", "name_en": "HYBE"},
    {"code": "069500", "market": "KS", "name_kr": "KODEX 200", "name_en": "KODEX 200 ETF"},
    {"code": "114800", "market": "KS", "name_kr": "KODEX 인버스", "name_en": "KODEX Inverse ETF"},
    {"code": "371460", "market": "KS", "name_kr": "TIGER 차이나전기차", "name_en": "TIGER China EV ETF"},

    # === KOSDAQ (.KQ) ===
    {"code": "035720", "market": "KQ", "name_kr": "카카오", "name_en": "Kakao"},
    {"code": "035420", "market": "KQ", "name_kr": "카카오뱅크", "name_en": "KakaoBank"},
    {"code": "263750", "market": "KQ", "name_kr": "펄어비스", "name_en": "Pearl Abyss"},
    {"code": "293490", "market": "KQ", "name_kr": "카카오게임즈", "name_en": "Kakao Games"},
    {"code": "068270", "market": "KQ", "name_kr": "셀트리온", "name_en": "Celltrion"},
    {"code": "247540", "market": "KQ", "name_kr": "에코프로비엠", "name_en": "EcoPro BM"},
    {"code": "086520", "market": "KQ", "name_kr": "에코프로", "name_en": "EcoPro"},
    {"code": "041510", "market": "KQ", "name_kr": "에스엠", "name_en": "SM Entertainment"},
    {"code": "112040", "market": "KQ", "name_kr": "위메이드", "name_en": "Wemade"},
    {"code": "376300", "market": "KQ", "name_kr": "디어유", "name_en": "Dear U"},
    {"code": "196170", "market": "KQ", "name_kr": "알테오젠", "name_en": "Alteogen"},
    {"code": "403870", "market": "KQ", "name_kr": "HPSP", "name_en": "HPSP"},
    {"code": "357780", "market": "KQ", "name_kr": "솔브레인", "name_en": "Solbrainn"},
    {"code": "145020", "market": "KQ", "name_kr": "휴젤", "name_en": "Hugel"},
    {"code": "058470", "market": "KQ", "name_kr": "리노공업", "name_en": "Leeno Industrial"},
]

# Common US / Global tickers for quick lookup
GLOBAL_TICKERS = [
    # === US Tech ===
    {"code": "AAPL", "market": "US", "name_kr": "애플", "name_en": "Apple"},
    {"code": "MSFT", "market": "US", "name_kr": "마이크로소프트", "name_en": "Microsoft"},
    {"code": "GOOGL", "market": "US", "name_kr": "구글", "name_en": "Alphabet (Google)"},
    {"code": "AMZN", "market": "US", "name_kr": "아마존", "name_en": "Amazon"},
    {"code": "TSLA", "market": "US", "name_kr": "테슬라", "name_en": "Tesla"},
    {"code": "NVDA", "market": "US", "name_kr": "엔비디아", "name_en": "Nvidia"},
    {"code": "META", "market": "US", "name_kr": "메타", "name_en": "Meta Platforms"},
    {"code": "NFLX", "market": "US", "name_kr": "넷플릭스", "name_en": "Netflix"},
    {"code": "AMD", "market": "US", "name_kr": "AMD", "name_en": "Advanced Micro Devices"},
    {"code": "INTC", "market": "US", "name_kr": "인텔", "name_en": "Intel"},
    {"code": "CRM", "market": "US", "name_kr": "세일즈포스", "name_en": "Salesforce"},
    {"code": "ORCL", "market": "US", "name_kr": "오라클", "name_en": "Oracle"},
    {"code": "ADBE", "market": "US", "name_kr": "어도비", "name_en": "Adobe"},
    {"code": "CSCO", "market": "US", "name_kr": "시스코", "name_en": "Cisco Systems"},
    {"code": "AVGO", "market": "US", "name_kr": "브로드컴", "name_en": "Broadcom"},
    {"code": "QCOM", "market": "US", "name_kr": "퀄컴", "name_en": "Qualcomm"},
    {"code": "UBER", "market": "US", "name_kr": "우버", "name_en": "Uber Technologies"},
    {"code": "SHOP", "market": "US", "name_kr": "쇼피파이", "name_en": "Shopify"},
    {"code": "SNOW", "market": "US", "name_kr": "스노우플레이크", "name_en": "Snowflake"},
    {"code": "PLTR", "market": "US", "name_kr": "팔란티어", "name_en": "Palantir Technologies"},
    {"code": "ARM", "market": "US", "name_kr": "ARM홀딩스", "name_en": "ARM Holdings"},
    {"code": "MU", "market": "US", "name_kr": "마이크론", "name_en": "Micron Technology"},
    {"code": "PANW", "market": "US", "name_kr": "팔로알토네트웍스", "name_en": "Palo Alto Networks"},

    # === US Finance / Healthcare / Consumer ===
    {"code": "JPM", "market": "US", "name_kr": "JP모건", "name_en": "JPMorgan Chase"},
    {"code": "V", "market": "US", "name_kr": "비자", "name_en": "Visa"},
    {"code": "MA", "market": "US", "name_kr": "마스터카드", "name_en": "Mastercard"},
    {"code": "BAC", "market": "US", "name_kr": "뱅크오브아메리카", "name_en": "Bank of America"},
    {"code": "GS", "market": "US", "name_kr": "골드만삭스", "name_en": "Goldman Sachs"},
    {"code": "JNJ", "market": "US", "name_kr": "존슨앤존슨", "name_en": "Johnson & Johnson"},
    {"code": "UNH", "market": "US", "name_kr": "유나이티드헬스", "name_en": "UnitedHealth Group"},
    {"code": "PFE", "market": "US", "name_kr": "화이자", "name_en": "Pfizer"},
    {"code": "LLY", "market": "US", "name_kr": "일라이릴리", "name_en": "Eli Lilly"},
    {"code": "KO", "market": "US", "name_kr": "코카콜라", "name_en": "Coca-Cola"},
    {"code": "PEP", "market": "US", "name_kr": "펩시코", "name_en": "PepsiCo"},
    {"code": "MCD", "market": "US", "name_kr": "맥도날드", "name_en": "McDonald's"},
    {"code": "NKE", "market": "US", "name_kr": "나이키", "name_en": "Nike"},
    {"code": "DIS", "market": "US", "name_kr": "디즈니", "name_en": "Walt Disney"},
    {"code": "WMT", "market": "US", "name_kr": "월마트", "name_en": "Walmart"},
    {"code": "COST", "market": "US", "name_kr": "코스트코", "name_en": "Costco"},

    # === Energy / Industrial ===
    {"code": "XOM", "market": "US", "name_kr": "엑슨모빌", "name_en": "Exxon Mobil"},
    {"code": "CVX", "market": "US", "name_kr": "쉐브론", "name_en": "Chevron"},
    {"code": "BA", "market": "US", "name_kr": "보잉", "name_en": "Boeing"},
    {"code": "CAT", "market": "US", "name_kr": "캐터필러", "name_en": "Caterpillar"},

    # === Crypto ===
    {"code": "BTC-USD", "market": "CRYPTO", "name_kr": "비트코인", "name_en": "Bitcoin"},
    {"code": "ETH-USD", "market": "CRYPTO", "name_kr": "이더리움", "name_en": "Ethereum"},
    {"code": "SOL-USD", "market": "CRYPTO", "name_kr": "솔라나", "name_en": "Solana"},
    {"code": "XRP-USD", "market": "CRYPTO", "name_kr": "리플", "name_en": "Ripple XRP"},

    # === ETFs ===
    {"code": "SPY", "market": "US", "name_kr": "S&P 500 ETF", "name_en": "SPDR S&P 500 ETF"},
    {"code": "QQQ", "market": "US", "name_kr": "나스닥 100 ETF", "name_en": "Invesco QQQ"},
    {"code": "IWM", "market": "US", "name_kr": "러셀 2000 ETF", "name_en": "iShares Russell 2000 ETF"},
    {"code": "VTI", "market": "US", "name_kr": "미국 전체시장 ETF", "name_en": "Vanguard Total Stock Market ETF"},
    {"code": "ARKK", "market": "US", "name_kr": "ARK 혁신 ETF", "name_en": "ARK Innovation ETF"},
    {"code": "SOXL", "market": "US", "name_kr": "반도체 3배 레버리지", "name_en": "Direxion Semiconductor 3x Bull"},
    {"code": "TQQQ", "market": "US", "name_kr": "나스닥 3배 레버리지", "name_en": "ProShares UltraPro QQQ"},
]

ALL_TICKERS = KOREAN_TICKERS + GLOBAL_TICKERS

# Build a quick lookup dict for Korean stocks by code
KR_CODE_MAP: dict[str, dict] = {t["code"]: t for t in KOREAN_TICKERS}


def search_tickers(query: str, limit: int = 8) -> list[dict]:
    """
    Search tickers by code or name (Korean or English).
    Returns a list of matching ticker dicts with a 'ticker' field for yfinance.
    """
    q = query.strip().lower()
    if not q:
        return []

    results = []
    for t in ALL_TICKERS:
        score = 0
        code_lower = t["code"].lower()
        name_kr = t["name_kr"].lower()
        name_en = t["name_en"].lower()

        # Exact code match gets highest priority
        if code_lower == q:
            score = 100
        elif code_lower.startswith(q):
            score = 80
        elif q in code_lower:
            score = 60
        # Name matching
        elif q in name_kr:
            score = 70
        elif q in name_en:
            score = 65

        if score > 0:
            # Build the yfinance ticker string
            if t["market"] in ("KS", "KQ"):
                yf_ticker = f"{t['code']}.{t['market']}"
            else:
                yf_ticker = t["code"]

            results.append({
                "code": t["code"],
                "name_kr": t["name_kr"],
                "name_en": t["name_en"],
                "market": t["market"],
                "ticker": yf_ticker,
                "_score": score,
            })

    # Sort by score descending, then by code
    results.sort(key=lambda x: (-x["_score"], x["code"]))

    # Remove internal score field
    for r in results[:limit]:
        del r["_score"]

    return results[:limit]


def resolve_ticker(raw: str) -> str:
    """
    Resolve a raw input string to a proper yfinance ticker.
    - 6-digit numbers → lookup in KR_CODE_MAP for correct .KS/.KQ suffix
    - Already has suffix (.KS, .KQ) → use as-is
    - Otherwise → pass through (US stocks, crypto, etc.)
    """
    raw = raw.strip()
    if raw.isdigit() and len(raw) == 6:
        info = KR_CODE_MAP.get(raw)
        if info:
            return f"{raw}.{info['market']}"
        return f"{raw}.KS"  # Default to KOSPI if not found in dict

    return raw
