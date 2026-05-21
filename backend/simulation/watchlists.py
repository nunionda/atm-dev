"""
멀티마켓 워치리스트 정의.
각 마켓별 종목 유니버스 + 포트폴리오 설정.
"""

from typing import Any, Dict, List

MarketId = str  # "kospi" | "sp500" | "ndx"

# ── KOSPI 200 구성종목 (시가총액 상위 ~100종목) ──

KOSPI_WATCHLIST: List[Dict[str, str]] = [
    # ── 반도체 ──
    {"code": "005930", "ticker": "005930.KS", "name": "삼성전자", "sector": "반도체"},
    {"code": "000660", "ticker": "000660.KS", "name": "SK하이닉스", "sector": "반도체"},
    {"code": "009150", "ticker": "009150.KS", "name": "삼성전기", "sector": "반도체"},
    {"code": "042700", "ticker": "042700.KS", "name": "한미반도체", "sector": "반도체"},
    # ── 자동차 ──
    {"code": "005380", "ticker": "005380.KS", "name": "현대자동차", "sector": "자동차"},
    {"code": "000270", "ticker": "000270.KS", "name": "기아", "sector": "자동차"},
    {"code": "012330", "ticker": "012330.KS", "name": "현대모비스", "sector": "자동차"},
    {"code": "018880", "ticker": "018880.KS", "name": "한온시스템", "sector": "자동차"},
    {"code": "161390", "ticker": "161390.KS", "name": "한국타이어앤테크놀로지", "sector": "자동차"},
    # ── IT / 플랫폼 ──
    {"code": "035420", "ticker": "035420.KS", "name": "NAVER", "sector": "IT"},
    {"code": "035720", "ticker": "035720.KS", "name": "카카오", "sector": "IT"},
    {"code": "018260", "ticker": "018260.KS", "name": "삼성에스디에스", "sector": "IT"},
    {"code": "377300", "ticker": "377300.KS", "name": "카카오페이", "sector": "IT"},
    # ── 바이오 / 헬스케어 ──
    {"code": "207940", "ticker": "207940.KS", "name": "삼성바이오로직스", "sector": "바이오"},
    {"code": "068270", "ticker": "068270.KS", "name": "셀트리온", "sector": "바이오"},
    {"code": "326030", "ticker": "326030.KS", "name": "SK바이오팜", "sector": "바이오"},
    {"code": "128940", "ticker": "128940.KS", "name": "한미약품", "sector": "바이오"},
    {"code": "006280", "ticker": "006280.KS", "name": "녹십자", "sector": "바이오"},
    {"code": "302440", "ticker": "302440.KS", "name": "SK바이오사이언스", "sector": "바이오"},
    # ── 화학 / 배터리 ──
    {"code": "051910", "ticker": "051910.KS", "name": "LG화학", "sector": "화학"},
    {"code": "006400", "ticker": "006400.KS", "name": "삼성SDI", "sector": "배터리"},
    {"code": "003670", "ticker": "003670.KS", "name": "포스코퓨처엠", "sector": "배터리"},
    {"code": "361610", "ticker": "361610.KS", "name": "SK아이이테크놀로지", "sector": "배터리"},
    {"code": "011170", "ticker": "011170.KS", "name": "롯데케미칼", "sector": "화학"},
    {"code": "006120", "ticker": "006120.KS", "name": "SK디스커버리", "sector": "화학"},
    # ── 금융 ──
    {"code": "105560", "ticker": "105560.KS", "name": "KB금융", "sector": "금융"},
    {"code": "055550", "ticker": "055550.KS", "name": "신한지주", "sector": "금융"},
    {"code": "086790", "ticker": "086790.KS", "name": "하나금융지주", "sector": "금융"},
    {"code": "316140", "ticker": "316140.KS", "name": "우리금융지주", "sector": "금융"},
    {"code": "138040", "ticker": "138040.KS", "name": "메리츠금융지주", "sector": "금융"},
    {"code": "032830", "ticker": "032830.KS", "name": "삼성생명", "sector": "금융"},
    {"code": "000810", "ticker": "000810.KS", "name": "삼성화재", "sector": "금융"},
    {"code": "024110", "ticker": "024110.KS", "name": "기업은행", "sector": "금융"},
    {"code": "006800", "ticker": "006800.KS", "name": "미래에셋증권", "sector": "금융"},
    # {"code": "003410", "ticker": "003410.KS", "name": "쌍용C&E", "sector": "금융"},  # 상장폐지
    # ── 전자 / 전기 ──
    {"code": "066570", "ticker": "066570.KS", "name": "LG전자", "sector": "전자"},
    {"code": "010120", "ticker": "010120.KS", "name": "LS일렉트릭", "sector": "전자"},
    {"code": "009450", "ticker": "009450.KS", "name": "경동나비엔", "sector": "전자"},
    # ── 소재 / 철강 ──
    {"code": "005490", "ticker": "005490.KS", "name": "POSCO홀딩스", "sector": "소재"},
    {"code": "010130", "ticker": "010130.KS", "name": "고려아연", "sector": "소재"},
    {"code": "004020", "ticker": "004020.KS", "name": "현대제철", "sector": "소재"},
    {"code": "010140", "ticker": "010140.KS", "name": "한솔제지", "sector": "소재"},
    # ── 산업재 / 조선 / 방산 ──
    {"code": "028260", "ticker": "028260.KS", "name": "삼성물산", "sector": "산업재"},
    {"code": "047050", "ticker": "047050.KS", "name": "포스코인터내셔널", "sector": "산업재"},
    {"code": "009540", "ticker": "009540.KS", "name": "한국조선해양", "sector": "산업재"},
    {"code": "267250", "ticker": "267250.KS", "name": "HD현대", "sector": "산업재"},
    {"code": "329180", "ticker": "329180.KS", "name": "HD현대중공업", "sector": "산업재"},
    {"code": "034020", "ticker": "034020.KS", "name": "두산에너빌리티", "sector": "산업재"},
    {"code": "042660", "ticker": "042660.KS", "name": "한화오션", "sector": "산업재"},
    {"code": "012450", "ticker": "012450.KS", "name": "한화에어로스페이스", "sector": "방산"},
    {"code": "047810", "ticker": "047810.KS", "name": "한국항공우주", "sector": "방산"},
    {"code": "079550", "ticker": "079550.KS", "name": "LIG넥스원", "sector": "방산"},
    # ── 에너지 ──
    {"code": "096770", "ticker": "096770.KS", "name": "SK이노베이션", "sector": "에너지"},
    {"code": "010950", "ticker": "010950.KS", "name": "S-Oil", "sector": "에너지"},
    {"code": "078930", "ticker": "078930.KS", "name": "GS", "sector": "에너지"},
    # ── 지주 ──
    {"code": "034730", "ticker": "034730.KS", "name": "SK", "sector": "지주"},
    {"code": "003550", "ticker": "003550.KS", "name": "LG", "sector": "지주"},
    # ── 통신 ──
    {"code": "017670", "ticker": "017670.KS", "name": "SK텔레콤", "sector": "통신"},
    {"code": "030200", "ticker": "030200.KS", "name": "KT", "sector": "통신"},
    {"code": "032640", "ticker": "032640.KS", "name": "LG유플러스", "sector": "통신"},
    # ── 운송 / 물류 ──
    {"code": "011200", "ticker": "011200.KS", "name": "HMM", "sector": "운송"},
    {"code": "003490", "ticker": "003490.KS", "name": "대한항공", "sector": "운송"},
    {"code": "020560", "ticker": "020560.KS", "name": "아시아나항공", "sector": "운송"},
    # ── 소비재 ──
    {"code": "033780", "ticker": "033780.KS", "name": "KT&G", "sector": "소비재"},
    {"code": "004170", "ticker": "004170.KS", "name": "신세계", "sector": "소비재"},
    {"code": "139480", "ticker": "139480.KS", "name": "이마트", "sector": "소비재"},
    {"code": "069960", "ticker": "069960.KS", "name": "현대백화점", "sector": "소비재"},
    {"code": "051900", "ticker": "051900.KS", "name": "LG생활건강", "sector": "소비재"},
    {"code": "090430", "ticker": "090430.KS", "name": "아모레퍼시픽", "sector": "소비재"},
    # ── 식품 ──
    {"code": "097950", "ticker": "097950.KS", "name": "CJ제일제당", "sector": "식품"},
    {"code": "271560", "ticker": "271560.KS", "name": "오리온", "sector": "식품"},
    {"code": "005300", "ticker": "005300.KS", "name": "롯데칠성", "sector": "식품"},
    # ── 건설 ──
    {"code": "000720", "ticker": "000720.KS", "name": "현대건설", "sector": "건설"},
    {"code": "006360", "ticker": "006360.KS", "name": "GS건설", "sector": "건설"},
    {"code": "047040", "ticker": "047040.KS", "name": "대우건설", "sector": "건설"},
    # ── 유틸리티 ──
    {"code": "015760", "ticker": "015760.KS", "name": "한국전력", "sector": "유틸리티"},
    {"code": "036460", "ticker": "036460.KS", "name": "한국가스공사", "sector": "유틸리티"},
    # ── 게임 / 엔터 ──
    {"code": "036570", "ticker": "036570.KS", "name": "엔씨소프트", "sector": "게임"},
    {"code": "259960", "ticker": "259960.KS", "name": "크래프톤", "sector": "게임"},
    {"code": "263750", "ticker": "263750.KQ", "name": "펄어비스", "sector": "게임"},  # KOSDAQ
    {"code": "352820", "ticker": "352820.KS", "name": "하이브", "sector": "엔터"},
    {"code": "041510", "ticker": "041510.KQ", "name": "에스엠", "sector": "엔터"},     # KOSDAQ
    {"code": "035900", "ticker": "035900.KQ", "name": "JYP Ent.", "sector": "엔터"},   # KOSDAQ
    # ── 기타 대형주 ──
    {"code": "000100", "ticker": "000100.KS", "name": "유한양행", "sector": "바이오"},
    {"code": "009830", "ticker": "009830.KS", "name": "한화솔루션", "sector": "에너지"},
    {"code": "011790", "ticker": "011790.KS", "name": "SKC", "sector": "소재"},
    {"code": "241560", "ticker": "241560.KS", "name": "두산밥캣", "sector": "산업재"},
    {"code": "402340", "ticker": "402340.KS", "name": "SK스퀘어", "sector": "지주"},
    {"code": "000120", "ticker": "000120.KS", "name": "CJ대한통운", "sector": "운송"},
    {"code": "011070", "ticker": "011070.KS", "name": "LG이노텍", "sector": "전자"},
    {"code": "016360", "ticker": "016360.KS", "name": "삼성증권", "sector": "금융"},
    {"code": "004990", "ticker": "004990.KS", "name": "롯데지주", "sector": "지주"},
    {"code": "307950", "ticker": "307950.KS", "name": "현대오토에버", "sector": "IT"},
    {"code": "383220", "ticker": "383220.KS", "name": "F&F", "sector": "소비재"},
    {"code": "005830", "ticker": "005830.KS", "name": "DB손해보험", "sector": "금융"},
    {"code": "001450", "ticker": "001450.KS", "name": "현대해상", "sector": "금융"},
    {"code": "180640", "ticker": "180640.KS", "name": "한진칼", "sector": "운송"},
    {"code": "003230", "ticker": "003230.KS", "name": "삼양식품", "sector": "식품"},
    {"code": "112610", "ticker": "112610.KS", "name": "씨에스윈드", "sector": "산업재"},
]

# ── S&P 500 시가총액 상위 100종목 ──
# 참고: 시가총액 순위는 시점에 따라 변동. yfinance에서 delisted 시 자동 skip되도록 SimEngine 처리.

SP500_WATCHLIST: List[Dict[str, str]] = [
    # ── Mega-cap Tech (시총 상위) ──
    {"code": "AAPL",  "ticker": "AAPL",  "name": "Apple",                 "sector": "Tech"},
    {"code": "MSFT",  "ticker": "MSFT",  "name": "Microsoft",             "sector": "Tech"},
    {"code": "NVDA",  "ticker": "NVDA",  "name": "NVIDIA",                "sector": "Semicon"},
    {"code": "GOOGL", "ticker": "GOOGL", "name": "Alphabet",              "sector": "CommSvc"},
    {"code": "AMZN",  "ticker": "AMZN",  "name": "Amazon",                "sector": "ConsDisc"},
    {"code": "META",  "ticker": "META",  "name": "Meta Platforms",        "sector": "CommSvc"},
    {"code": "AVGO",  "ticker": "AVGO",  "name": "Broadcom",              "sector": "Semicon"},
    {"code": "TSLA",  "ticker": "TSLA",  "name": "Tesla",                 "sector": "ConsDisc"},
    {"code": "ORCL",  "ticker": "ORCL",  "name": "Oracle",                "sector": "Tech"},

    # ── Financials (Mega-cap) ──
    {"code": "BRK-B", "ticker": "BRK-B", "name": "Berkshire Hathaway",    "sector": "Financial"},
    {"code": "JPM",   "ticker": "JPM",   "name": "JPMorgan Chase",        "sector": "Financial"},
    {"code": "V",     "ticker": "V",     "name": "Visa",                  "sector": "Financial"},
    {"code": "MA",    "ticker": "MA",    "name": "Mastercard",            "sector": "Financial"},
    {"code": "BAC",   "ticker": "BAC",   "name": "Bank of America",       "sector": "Financial"},
    {"code": "WFC",   "ticker": "WFC",   "name": "Wells Fargo",           "sector": "Financial"},
    {"code": "GS",    "ticker": "GS",    "name": "Goldman Sachs",         "sector": "Financial"},
    {"code": "MS",    "ticker": "MS",    "name": "Morgan Stanley",        "sector": "Financial"},
    {"code": "AXP",   "ticker": "AXP",   "name": "American Express",      "sector": "Financial"},
    {"code": "BLK",   "ticker": "BLK",   "name": "BlackRock",             "sector": "Financial"},
    {"code": "SCHW",  "ticker": "SCHW",  "name": "Charles Schwab",        "sector": "Financial"},
    {"code": "C",     "ticker": "C",     "name": "Citigroup",             "sector": "Financial"},
    {"code": "SPGI",  "ticker": "SPGI",  "name": "S&P Global",            "sector": "Financial"},
    {"code": "PGR",   "ticker": "PGR",   "name": "Progressive",           "sector": "Financial"},
    {"code": "CB",    "ticker": "CB",    "name": "Chubb",                 "sector": "Financial"},
    # {"code": "MMC",   "ticker": "MMC",   "name": "Marsh & McLennan",      "sector": "Financial"},  # 비활성: 야후 지속 fail (3회 retry 모두 rate limit, AAPL 등은 정상) — 야후 복구 시 주석 해제
    {"code": "KKR",   "ticker": "KKR",   "name": "KKR",                   "sector": "Financial"},
    {"code": "BX",    "ticker": "BX",    "name": "Blackstone",            "sector": "Financial"},
    {"code": "FISV",  "ticker": "FISV",  "name": "Fiserv",                "sector": "Financial"},  # P3-3: FI → FISV (야후가 신규 ticker 미지원, historical FISV 정상)

    # ── Healthcare ──
    {"code": "LLY",   "ticker": "LLY",   "name": "Eli Lilly",             "sector": "Health"},
    {"code": "UNH",   "ticker": "UNH",   "name": "UnitedHealth",          "sector": "Health"},
    {"code": "JNJ",   "ticker": "JNJ",   "name": "Johnson & Johnson",     "sector": "Health"},
    {"code": "ABBV",  "ticker": "ABBV",  "name": "AbbVie",                "sector": "Health"},
    {"code": "MRK",   "ticker": "MRK",   "name": "Merck",                 "sector": "Health"},
    {"code": "TMO",   "ticker": "TMO",   "name": "Thermo Fisher",         "sector": "Health"},
    {"code": "ABT",   "ticker": "ABT",   "name": "Abbott Labs",           "sector": "Health"},
    {"code": "DHR",   "ticker": "DHR",   "name": "Danaher",               "sector": "Health"},
    {"code": "PFE",   "ticker": "PFE",   "name": "Pfizer",                "sector": "Health"},
    {"code": "AMGN",  "ticker": "AMGN",  "name": "Amgen",                 "sector": "Health"},
    {"code": "ISRG",  "ticker": "ISRG",  "name": "Intuitive Surgical",    "sector": "Health"},
    {"code": "SYK",   "ticker": "SYK",   "name": "Stryker",               "sector": "Health"},
    {"code": "BSX",   "ticker": "BSX",   "name": "Boston Scientific",     "sector": "Health"},
    {"code": "GILD",  "ticker": "GILD",  "name": "Gilead Sciences",       "sector": "Health"},
    {"code": "ELV",   "ticker": "ELV",   "name": "Elevance Health",       "sector": "Health"},
    {"code": "VRTX",  "ticker": "VRTX",  "name": "Vertex Pharma",         "sector": "Health"},
    {"code": "REGN",  "ticker": "REGN",  "name": "Regeneron",             "sector": "Health"},
    {"code": "CI",    "ticker": "CI",    "name": "Cigna",                 "sector": "Health"},
    {"code": "ZTS",   "ticker": "ZTS",   "name": "Zoetis",                "sector": "Health"},

    # ── Consumer ──
    {"code": "WMT",   "ticker": "WMT",   "name": "Walmart",               "sector": "ConsStaple"},
    {"code": "COST",  "ticker": "COST",  "name": "Costco",                "sector": "ConsStaple"},
    {"code": "PG",    "ticker": "PG",    "name": "Procter & Gamble",      "sector": "ConsStaple"},
    {"code": "HD",    "ticker": "HD",    "name": "Home Depot",            "sector": "ConsDisc"},
    {"code": "KO",    "ticker": "KO",    "name": "Coca-Cola",             "sector": "ConsStaple"},
    {"code": "PEP",   "ticker": "PEP",   "name": "PepsiCo",               "sector": "ConsStaple"},
    {"code": "MCD",   "ticker": "MCD",   "name": "McDonald's",            "sector": "ConsDisc"},
    {"code": "LOW",   "ticker": "LOW",   "name": "Lowe's",                "sector": "ConsDisc"},
    {"code": "PM",    "ticker": "PM",    "name": "Philip Morris",         "sector": "ConsStaple"},
    {"code": "MDLZ",  "ticker": "MDLZ",  "name": "Mondelez",              "sector": "ConsStaple"},
    {"code": "MO",    "ticker": "MO",    "name": "Altria",                "sector": "ConsStaple"},
    {"code": "TJX",   "ticker": "TJX",   "name": "TJX Companies",         "sector": "ConsDisc"},
    {"code": "BKNG",  "ticker": "BKNG",  "name": "Booking Holdings",      "sector": "ConsDisc"},
    {"code": "UBER",  "ticker": "UBER",  "name": "Uber",                  "sector": "Industrial"},

    # ── Tech / Semicon / Software ──
    {"code": "CRM",   "ticker": "CRM",   "name": "Salesforce",            "sector": "Tech"},
    {"code": "AMD",   "ticker": "AMD",   "name": "AMD",                   "sector": "Semicon"},
    {"code": "ADBE",  "ticker": "ADBE",  "name": "Adobe",                 "sector": "Tech"},
    {"code": "ACN",   "ticker": "ACN",   "name": "Accenture",             "sector": "Tech"},
    {"code": "CSCO",  "ticker": "CSCO",  "name": "Cisco",                 "sector": "Tech"},
    {"code": "IBM",   "ticker": "IBM",   "name": "IBM",                   "sector": "Tech"},
    {"code": "TXN",   "ticker": "TXN",   "name": "Texas Instruments",     "sector": "Semicon"},
    {"code": "INTU",  "ticker": "INTU",  "name": "Intuit",                "sector": "Tech"},
    {"code": "QCOM",  "ticker": "QCOM",  "name": "Qualcomm",              "sector": "Semicon"},
    {"code": "AMAT",  "ticker": "AMAT",  "name": "Applied Materials",     "sector": "Semicon"},
    {"code": "ADI",   "ticker": "ADI",   "name": "Analog Devices",        "sector": "Semicon"},
    {"code": "MU",    "ticker": "MU",    "name": "Micron",                "sector": "Semicon"},
    {"code": "KLAC",  "ticker": "KLAC",  "name": "KLA Corp",              "sector": "Semicon"},
    {"code": "NOW",   "ticker": "NOW",   "name": "ServiceNow",            "sector": "Tech"},
    {"code": "ANET",  "ticker": "ANET",  "name": "Arista Networks",       "sector": "Tech"},
    {"code": "PANW",  "ticker": "PANW",  "name": "Palo Alto Networks",    "sector": "Tech"},
    {"code": "ADP",   "ticker": "ADP",   "name": "Automatic Data Proc",   "sector": "Tech"},
    {"code": "PYPL",  "ticker": "PYPL",  "name": "PayPal",                "sector": "Financial"},
    {"code": "INTC",  "ticker": "INTC",  "name": "Intel",                 "sector": "Semicon"},

    # ── CommSvc / Media ──
    {"code": "NFLX",  "ticker": "NFLX",  "name": "Netflix",               "sector": "CommSvc"},
    {"code": "CMCSA", "ticker": "CMCSA", "name": "Comcast",               "sector": "CommSvc"},
    {"code": "VZ",    "ticker": "VZ",    "name": "Verizon",               "sector": "CommSvc"},
    {"code": "T",     "ticker": "T",     "name": "AT&T",                  "sector": "CommSvc"},

    # ── Industrial ──
    {"code": "GE",    "ticker": "GE",    "name": "GE Aerospace",          "sector": "Industrial"},
    {"code": "CAT",   "ticker": "CAT",   "name": "Caterpillar",           "sector": "Industrial"},
    {"code": "RTX",   "ticker": "RTX",   "name": "RTX Corp",              "sector": "Industrial"},
    {"code": "HON",   "ticker": "HON",   "name": "Honeywell",             "sector": "Industrial"},
    {"code": "UNP",   "ticker": "UNP",   "name": "Union Pacific",         "sector": "Industrial"},
    {"code": "ETN",   "ticker": "ETN",   "name": "Eaton",                 "sector": "Industrial"},
    {"code": "DE",    "ticker": "DE",    "name": "Deere",                 "sector": "Industrial"},
    {"code": "LMT",   "ticker": "LMT",   "name": "Lockheed Martin",       "sector": "Industrial"},
    {"code": "UPS",   "ticker": "UPS",   "name": "United Parcel Service", "sector": "Industrial"},

    # ── Energy / Utilities / Materials ──
    {"code": "XOM",   "ticker": "XOM",   "name": "Exxon Mobil",           "sector": "Energy"},
    {"code": "CVX",   "ticker": "CVX",   "name": "Chevron",               "sector": "Energy"},
    {"code": "NEE",   "ticker": "NEE",   "name": "NextEra Energy",        "sector": "Utilities"},
    {"code": "SO",    "ticker": "SO",    "name": "Southern Company",      "sector": "Utilities"},
    {"code": "DUK",   "ticker": "DUK",   "name": "Duke Energy",           "sector": "Utilities"},
    {"code": "LIN",   "ticker": "LIN",   "name": "Linde",                 "sector": "Materials"},

    # ── Real Estate ──
    {"code": "PLD",   "ticker": "PLD",   "name": "Prologis",              "sector": "RealEstate"},
]

# ── NASDAQ 100 시가총액 상위 100종목 ──
# NDX는 비금융 100개 구성 — 시가총액 가중 비중에서 상위 종목 우선 배치.

NDX_WATCHLIST: List[Dict[str, str]] = [
    # ── Mega-cap (NDX 가중 상위 7~10) ──
    {"code": "AAPL",  "ticker": "AAPL",  "name": "Apple",                 "sector": "Tech"},
    {"code": "MSFT",  "ticker": "MSFT",  "name": "Microsoft",             "sector": "Tech"},
    {"code": "NVDA",  "ticker": "NVDA",  "name": "NVIDIA",                "sector": "Semicon"},
    {"code": "AMZN",  "ticker": "AMZN",  "name": "Amazon",                "sector": "ConsDisc"},
    {"code": "AVGO",  "ticker": "AVGO",  "name": "Broadcom",              "sector": "Semicon"},
    {"code": "META",  "ticker": "META",  "name": "Meta Platforms",        "sector": "CommSvc"},
    {"code": "GOOGL", "ticker": "GOOGL", "name": "Alphabet (Class A)",    "sector": "CommSvc"},
    {"code": "GOOG",  "ticker": "GOOG",  "name": "Alphabet (Class C)",    "sector": "CommSvc"},
    {"code": "TSLA",  "ticker": "TSLA",  "name": "Tesla",                 "sector": "ConsDisc"},
    {"code": "NFLX",  "ticker": "NFLX",  "name": "Netflix",               "sector": "CommSvc"},

    # ── Large-cap Tech / Semicon ──
    {"code": "COST",  "ticker": "COST",  "name": "Costco",                "sector": "ConsStaple"},
    {"code": "ADBE",  "ticker": "ADBE",  "name": "Adobe",                 "sector": "Tech"},
    {"code": "PEP",   "ticker": "PEP",   "name": "PepsiCo",               "sector": "ConsStaple"},
    {"code": "CSCO",  "ticker": "CSCO",  "name": "Cisco",                 "sector": "Tech"},
    {"code": "AMD",   "ticker": "AMD",   "name": "AMD",                   "sector": "Semicon"},
    {"code": "TMUS",  "ticker": "TMUS",  "name": "T-Mobile US",           "sector": "CommSvc"},
    {"code": "CMCSA", "ticker": "CMCSA", "name": "Comcast",               "sector": "CommSvc"},
    {"code": "QCOM",  "ticker": "QCOM",  "name": "Qualcomm",              "sector": "Semicon"},
    {"code": "INTU",  "ticker": "INTU",  "name": "Intuit",                "sector": "Tech"},
    {"code": "TXN",   "ticker": "TXN",   "name": "Texas Instruments",     "sector": "Semicon"},
    {"code": "AMGN",  "ticker": "AMGN",  "name": "Amgen",                 "sector": "Health"},
    {"code": "ISRG",  "ticker": "ISRG",  "name": "Intuitive Surgical",    "sector": "Health"},
    {"code": "AMAT",  "ticker": "AMAT",  "name": "Applied Materials",     "sector": "Semicon"},
    {"code": "BKNG",  "ticker": "BKNG",  "name": "Booking Holdings",      "sector": "ConsDisc"},
    {"code": "HON",   "ticker": "HON",   "name": "Honeywell",             "sector": "Industrial"},

    # ── Mid-large Tech / Semicon ──
    {"code": "MU",    "ticker": "MU",    "name": "Micron",                "sector": "Semicon"},
    {"code": "ADI",   "ticker": "ADI",   "name": "Analog Devices",        "sector": "Semicon"},
    {"code": "LRCX",  "ticker": "LRCX",  "name": "Lam Research",          "sector": "Semicon"},
    {"code": "VRTX",  "ticker": "VRTX",  "name": "Vertex Pharma",         "sector": "Health"},
    {"code": "PANW",  "ticker": "PANW",  "name": "Palo Alto Networks",    "sector": "Tech"},
    {"code": "KLAC",  "ticker": "KLAC",  "name": "KLA Corp",              "sector": "Semicon"},
    {"code": "REGN",  "ticker": "REGN",  "name": "Regeneron",             "sector": "Health"},
    {"code": "PYPL",  "ticker": "PYPL",  "name": "PayPal",                "sector": "Financial"},
    {"code": "ADP",   "ticker": "ADP",   "name": "Automatic Data Proc",   "sector": "Tech"},
    {"code": "SBUX",  "ticker": "SBUX",  "name": "Starbucks",             "sector": "ConsDisc"},
    {"code": "MDLZ",  "ticker": "MDLZ",  "name": "Mondelez",              "sector": "ConsStaple"},
    {"code": "GILD",  "ticker": "GILD",  "name": "Gilead Sciences",       "sector": "Health"},
    {"code": "ABNB",  "ticker": "ABNB",  "name": "Airbnb",                "sector": "ConsDisc"},
    {"code": "INTC",  "ticker": "INTC",  "name": "Intel",                 "sector": "Semicon"},
    {"code": "MELI",  "ticker": "MELI",  "name": "MercadoLibre",          "sector": "ConsDisc"},

    # ── Software / Cloud ──
    {"code": "PDD",   "ticker": "PDD",   "name": "PDD Holdings",          "sector": "ConsDisc"},
    {"code": "SNPS",  "ticker": "SNPS",  "name": "Synopsys",              "sector": "Tech"},
    {"code": "CTAS",  "ticker": "CTAS",  "name": "Cintas",                "sector": "Industrial"},
    {"code": "CDNS",  "ticker": "CDNS",  "name": "Cadence Design",        "sector": "Tech"},
    {"code": "MAR",   "ticker": "MAR",   "name": "Marriott Intl",         "sector": "ConsDisc"},
    {"code": "ORLY",  "ticker": "ORLY",  "name": "O'Reilly Automotive",   "sector": "ConsDisc"},
    {"code": "ASML",  "ticker": "ASML",  "name": "ASML",                  "sector": "Semicon"},
    {"code": "CSX",   "ticker": "CSX",   "name": "CSX Corp",              "sector": "Industrial"},
    {"code": "FTNT",  "ticker": "FTNT",  "name": "Fortinet",              "sector": "Tech"},
    {"code": "ROP",   "ticker": "ROP",   "name": "Roper Tech",            "sector": "Tech"},
    {"code": "AEP",   "ticker": "AEP",   "name": "American Electric Pwr", "sector": "Utilities"},
    {"code": "NXPI",  "ticker": "NXPI",  "name": "NXP Semiconductors",    "sector": "Semicon"},
    {"code": "PCAR",  "ticker": "PCAR",  "name": "PACCAR",                "sector": "Industrial"},
    {"code": "MNST",  "ticker": "MNST",  "name": "Monster Beverage",      "sector": "ConsStaple"},
    {"code": "AZN",   "ticker": "AZN",   "name": "AstraZeneca",           "sector": "Health"},

    # ── Tech / Cloud / Workforce ──
    {"code": "WDAY",  "ticker": "WDAY",  "name": "Workday",               "sector": "Tech"},
    {"code": "ROST",  "ticker": "ROST",  "name": "Ross Stores",           "sector": "ConsDisc"},
    {"code": "KDP",   "ticker": "KDP",   "name": "Keurig Dr Pepper",      "sector": "ConsStaple"},
    {"code": "ADSK",  "ticker": "ADSK",  "name": "Autodesk",              "sector": "Tech"},
    {"code": "FAST",  "ticker": "FAST",  "name": "Fastenal",              "sector": "Industrial"},
    {"code": "PAYX",  "ticker": "PAYX",  "name": "Paychex",               "sector": "Tech"},
    {"code": "CHTR",  "ticker": "CHTR",  "name": "Charter Communications","sector": "CommSvc"},
    {"code": "ODFL",  "ticker": "ODFL",  "name": "Old Dominion Freight",  "sector": "Industrial"},
    {"code": "TTD",   "ticker": "TTD",   "name": "The Trade Desk",        "sector": "Tech"},
    {"code": "CPRT",  "ticker": "CPRT",  "name": "Copart",                "sector": "Industrial"},
    {"code": "EXC",   "ticker": "EXC",   "name": "Exelon",                "sector": "Utilities"},
    {"code": "EA",    "ticker": "EA",    "name": "Electronic Arts",       "sector": "CommSvc"},
    {"code": "DDOG",  "ticker": "DDOG",  "name": "Datadog",               "sector": "Tech"},
    {"code": "CRWD",  "ticker": "CRWD",  "name": "CrowdStrike",           "sector": "Tech"},
    {"code": "KHC",   "ticker": "KHC",   "name": "Kraft Heinz",           "sector": "ConsStaple"},

    # ── Mid-cap NDX ──
    {"code": "CCEP",  "ticker": "CCEP",  "name": "Coca-Cola Europacific", "sector": "ConsStaple"},
    {"code": "CTSH",  "ticker": "CTSH",  "name": "Cognizant",             "sector": "Tech"},
    {"code": "VRSK",  "ticker": "VRSK",  "name": "Verisk Analytics",      "sector": "Industrial"},
    {"code": "XEL",   "ticker": "XEL",   "name": "Xcel Energy",           "sector": "Utilities"},
    {"code": "FANG",  "ticker": "FANG",  "name": "Diamondback Energy",    "sector": "Energy"},
    {"code": "BKR",   "ticker": "BKR",   "name": "Baker Hughes",          "sector": "Energy"},
    {"code": "IDXX",  "ticker": "IDXX",  "name": "IDEXX Laboratories",    "sector": "Health"},
    {"code": "ZS",    "ticker": "ZS",    "name": "Zscaler",               "sector": "Tech"},
    {"code": "CSGP",  "ticker": "CSGP",  "name": "CoStar Group",          "sector": "Industrial"},
    {"code": "DXCM",  "ticker": "DXCM",  "name": "DexCom",                "sector": "Health"},
    {"code": "CDW",   "ticker": "CDW",   "name": "CDW Corp",              "sector": "Tech"},
    # ANSS (ANSYS)는 2025-01 Synopsys 인수 완료로 delisted. SNPS로 대체 — 이미 포함됨.
    {"code": "ALGN",  "ticker": "ALGN",  "name": "Align Technology",      "sector": "Health"},
    {"code": "ON",    "ticker": "ON",    "name": "ON Semiconductor",      "sector": "Semicon"},
    {"code": "TEAM",  "ticker": "TEAM",  "name": "Atlassian",             "sector": "Tech"},
    {"code": "GFS",   "ticker": "GFS",   "name": "GlobalFoundries",       "sector": "Semicon"},
    {"code": "WBD",   "ticker": "WBD",   "name": "Warner Bros Discovery", "sector": "CommSvc"},
    {"code": "MDB",   "ticker": "MDB",   "name": "MongoDB",               "sector": "Tech"},
    {"code": "TTWO",  "ticker": "TTWO",  "name": "Take-Two Interactive",  "sector": "CommSvc"},
    {"code": "BIIB",  "ticker": "BIIB",  "name": "Biogen",                "sector": "Health"},
    {"code": "ARM",   "ticker": "ARM",   "name": "ARM Holdings",          "sector": "Semicon"},
    {"code": "MRVL",  "ticker": "MRVL",  "name": "Marvell Tech",          "sector": "Semicon"},
    {"code": "DASH",  "ticker": "DASH",  "name": "DoorDash",              "sector": "ConsDisc"},
    {"code": "ILMN",  "ticker": "ILMN",  "name": "Illumina",              "sector": "Health"},
    {"code": "LULU",  "ticker": "LULU",  "name": "Lululemon Athletica",   "sector": "ConsDisc"},
    {"code": "SIRI",  "ticker": "SIRI",  "name": "Sirius XM",             "sector": "CommSvc"},
    {"code": "GEHC",  "ticker": "GEHC",  "name": "GE HealthCare",         "sector": "Health"},
    {"code": "DLTR",  "ticker": "DLTR",  "name": "Dollar Tree",           "sector": "ConsStaple"},
    {"code": "AKAM",  "ticker": "AKAM",  "name": "Akamai Tech",           "sector": "Tech"},
    {"code": "SMCI",  "ticker": "SMCI",  "name": "Super Micro Computer",  "sector": "Tech"},
    {"code": "MCHP",  "ticker": "MCHP",  "name": "Microchip Technology",  "sector": "Semicon"},
]

# ── 마켓 설정 레지스트리 ──

MARKET_CONFIG: Dict[MarketId, Dict[str, Any]] = {
    "kospi": {
        "watchlist": KOSPI_WATCHLIST,          # ~100종목 (전체 tactical)
        "initial_capital": 100_000_000,       # ₩100M
        "currency": "KRW",
        "currency_symbol": "₩",
        "label": "KOSPI 200",
        "max_daily_trade_amount": 30_000_000,
        "strategy_mode": "momentum",          # momentum | smc | breakout_retest
        "index_symbol": "^KS200",             # KOSPI 200 지수 (추세 분석용)
        "vix_symbol": "^VIX",                 # VIX (변동성 레짐)
    },
    "sp500": {
        "watchlist": SP500_WATCHLIST,
        "initial_capital": 100_000,            # $100K
        "currency": "USD",
        "currency_symbol": "$",
        "label": "S&P 500",
        "max_daily_trade_amount": 30_000,
        "strategy_mode": "momentum",
        "index_symbol": "^GSPC",              # S&P 500 지수
        "vix_symbol": "^VIX",
    },
    "ndx": {
        "watchlist": NDX_WATCHLIST,
        "initial_capital": 100_000,            # $100K
        "currency": "USD",
        "currency_symbol": "$",
        "label": "NASDAQ 100",
        "max_daily_trade_amount": 30_000,
        "strategy_mode": "momentum",
        "index_symbol": "^IXIC",              # NASDAQ Composite 지수
        "vix_symbol": "^VIX",
    },
}

VALID_MARKETS = list(MARKET_CONFIG.keys())
