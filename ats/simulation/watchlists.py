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
    {"code": "263750", "ticker": "263750.KS", "name": "펄어비스", "sector": "게임"},
    {"code": "352820", "ticker": "352820.KS", "name": "하이브", "sector": "엔터"},
    {"code": "041510", "ticker": "041510.KS", "name": "에스엠", "sector": "엔터"},
    {"code": "035900", "ticker": "035900.KS", "name": "JYP Ent.", "sector": "엔터"},
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

# ── S&P 500 대표 20종목 (시가총액 상위) ──

SP500_WATCHLIST: List[Dict[str, str]] = [
    {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
    {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
    {"code": "AMZN", "ticker": "AMZN", "name": "Amazon", "sector": "ConsDisc"},
    {"code": "NVDA", "ticker": "NVDA", "name": "NVIDIA", "sector": "Tech"},
    {"code": "GOOGL", "ticker": "GOOGL", "name": "Alphabet", "sector": "CommSvc"},
    {"code": "META", "ticker": "META", "name": "Meta", "sector": "CommSvc"},
    {"code": "BRK-B", "ticker": "BRK-B", "name": "Berkshire Hathaway", "sector": "Financial"},
    {"code": "LLY", "ticker": "LLY", "name": "Eli Lilly", "sector": "Health"},
    {"code": "JPM", "ticker": "JPM", "name": "JPMorgan Chase", "sector": "Financial"},
    {"code": "V", "ticker": "V", "name": "Visa", "sector": "Financial"},
    {"code": "UNH", "ticker": "UNH", "name": "UnitedHealth", "sector": "Health"},
    {"code": "XOM", "ticker": "XOM", "name": "Exxon Mobil", "sector": "Energy"},
    {"code": "MA", "ticker": "MA", "name": "Mastercard", "sector": "Financial"},
    {"code": "JNJ", "ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Health"},
    {"code": "PG", "ticker": "PG", "name": "Procter & Gamble", "sector": "ConsStaple"},
    {"code": "HD", "ticker": "HD", "name": "Home Depot", "sector": "ConsDisc"},
    {"code": "COST", "ticker": "COST", "name": "Costco", "sector": "ConsStaple"},
    {"code": "ABBV", "ticker": "ABBV", "name": "AbbVie", "sector": "Health"},
    {"code": "CRM", "ticker": "CRM", "name": "Salesforce", "sector": "Tech"},
    {"code": "WMT", "ticker": "WMT", "name": "Walmart", "sector": "ConsStaple"},
]

# ── NASDAQ 100 대표 20종목 (시가총액 상위) ──

NDX_WATCHLIST: List[Dict[str, str]] = [
    {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
    {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
    {"code": "NVDA", "ticker": "NVDA", "name": "NVIDIA", "sector": "Semicon"},
    {"code": "AMZN", "ticker": "AMZN", "name": "Amazon", "sector": "ConsDisc"},
    {"code": "META", "ticker": "META", "name": "Meta", "sector": "CommSvc"},
    {"code": "GOOGL", "ticker": "GOOGL", "name": "Alphabet", "sector": "CommSvc"},
    {"code": "AVGO", "ticker": "AVGO", "name": "Broadcom", "sector": "Semicon"},
    {"code": "TSLA", "ticker": "TSLA", "name": "Tesla", "sector": "ConsDisc"},
    {"code": "ADBE", "ticker": "ADBE", "name": "Adobe", "sector": "Tech"},
    {"code": "NFLX", "ticker": "NFLX", "name": "Netflix", "sector": "CommSvc"},
    {"code": "AMD", "ticker": "AMD", "name": "AMD", "sector": "Semicon"},
    {"code": "INTC", "ticker": "INTC", "name": "Intel", "sector": "Semicon"},
    {"code": "QCOM", "ticker": "QCOM", "name": "Qualcomm", "sector": "Semicon"},
    {"code": "TXN", "ticker": "TXN", "name": "Texas Instruments", "sector": "Semicon"},
    {"code": "ISRG", "ticker": "ISRG", "name": "Intuitive Surgical", "sector": "Health"},
    {"code": "AMAT", "ticker": "AMAT", "name": "Applied Materials", "sector": "Semicon"},
    {"code": "BKNG", "ticker": "BKNG", "name": "Booking", "sector": "ConsDisc"},
    {"code": "MU", "ticker": "MU", "name": "Micron", "sector": "Semicon"},
    {"code": "LRCX", "ticker": "LRCX", "name": "Lam Research", "sector": "Semicon"},
    {"code": "PANW", "ticker": "PANW", "name": "Palo Alto Networks", "sector": "Tech"},
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
