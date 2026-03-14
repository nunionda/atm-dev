"""
유니버스 스캐너 + 구성종목 리스트.

전체 종목을 14거래일마다 스캔하여 모멘텀 상위 종목을 동적으로 선별한다.
2-Tier 시스템: Tier 1(UniverseScanner) → Tier 2(기존 6-Phase Engine)
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# ── S&P 500 구성종목 (시총 상위 ~105종목) ──
# 각 섹터별 대표 종목을 포함한 전체 유니버스
SP500_FULL: List[Dict[str, str]] = [
    # Technology (~20)
    {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
    {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
    {"code": "NVDA", "ticker": "NVDA", "name": "NVIDIA", "sector": "Tech"},
    {"code": "AVGO", "ticker": "AVGO", "name": "Broadcom", "sector": "Tech"},
    {"code": "CRM", "ticker": "CRM", "name": "Salesforce", "sector": "Tech"},
    {"code": "ADBE", "ticker": "ADBE", "name": "Adobe", "sector": "Tech"},
    {"code": "CSCO", "ticker": "CSCO", "name": "Cisco", "sector": "Tech"},
    {"code": "ACN", "ticker": "ACN", "name": "Accenture", "sector": "Tech"},
    {"code": "ORCL", "ticker": "ORCL", "name": "Oracle", "sector": "Tech"},
    {"code": "IBM", "ticker": "IBM", "name": "IBM", "sector": "Tech"},
    {"code": "INTC", "ticker": "INTC", "name": "Intel", "sector": "Tech"},
    {"code": "AMD", "ticker": "AMD", "name": "AMD", "sector": "Tech"},
    {"code": "QCOM", "ticker": "QCOM", "name": "Qualcomm", "sector": "Tech"},
    {"code": "TXN", "ticker": "TXN", "name": "Texas Instruments", "sector": "Tech"},
    {"code": "INTU", "ticker": "INTU", "name": "Intuit", "sector": "Tech"},
    {"code": "NOW", "ticker": "NOW", "name": "ServiceNow", "sector": "Tech"},
    {"code": "AMAT", "ticker": "AMAT", "name": "Applied Materials", "sector": "Tech"},
    {"code": "MU", "ticker": "MU", "name": "Micron", "sector": "Tech"},
    {"code": "LRCX", "ticker": "LRCX", "name": "Lam Research", "sector": "Tech"},
    {"code": "KLAC", "ticker": "KLAC", "name": "KLA Corp", "sector": "Tech"},
    # Healthcare (~15)
    {"code": "LLY", "ticker": "LLY", "name": "Eli Lilly", "sector": "Health"},
    {"code": "UNH", "ticker": "UNH", "name": "UnitedHealth", "sector": "Health"},
    {"code": "JNJ", "ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Health"},
    {"code": "ABBV", "ticker": "ABBV", "name": "AbbVie", "sector": "Health"},
    {"code": "MRK", "ticker": "MRK", "name": "Merck", "sector": "Health"},
    {"code": "PFE", "ticker": "PFE", "name": "Pfizer", "sector": "Health"},
    {"code": "TMO", "ticker": "TMO", "name": "Thermo Fisher", "sector": "Health"},
    {"code": "ABT", "ticker": "ABT", "name": "Abbott Labs", "sector": "Health"},
    {"code": "DHR", "ticker": "DHR", "name": "Danaher", "sector": "Health"},
    {"code": "AMGN", "ticker": "AMGN", "name": "Amgen", "sector": "Health"},
    {"code": "ISRG", "ticker": "ISRG", "name": "Intuitive Surgical", "sector": "Health"},
    {"code": "BMY", "ticker": "BMY", "name": "Bristol-Myers", "sector": "Health"},
    {"code": "GILD", "ticker": "GILD", "name": "Gilead Sciences", "sector": "Health"},
    {"code": "VRTX", "ticker": "VRTX", "name": "Vertex Pharma", "sector": "Health"},
    {"code": "MDT", "ticker": "MDT", "name": "Medtronic", "sector": "Health"},
    # Financial (~12)
    {"code": "BRK-B", "ticker": "BRK-B", "name": "Berkshire Hathaway", "sector": "Financial"},
    {"code": "JPM", "ticker": "JPM", "name": "JPMorgan Chase", "sector": "Financial"},
    {"code": "V", "ticker": "V", "name": "Visa", "sector": "Financial"},
    {"code": "MA", "ticker": "MA", "name": "Mastercard", "sector": "Financial"},
    {"code": "BAC", "ticker": "BAC", "name": "Bank of America", "sector": "Financial"},
    {"code": "WFC", "ticker": "WFC", "name": "Wells Fargo", "sector": "Financial"},
    {"code": "GS", "ticker": "GS", "name": "Goldman Sachs", "sector": "Financial"},
    {"code": "MS", "ticker": "MS", "name": "Morgan Stanley", "sector": "Financial"},
    {"code": "C", "ticker": "C", "name": "Citigroup", "sector": "Financial"},
    {"code": "BLK", "ticker": "BLK", "name": "BlackRock", "sector": "Financial"},
    {"code": "AXP", "ticker": "AXP", "name": "American Express", "sector": "Financial"},
    {"code": "SCHW", "ticker": "SCHW", "name": "Charles Schwab", "sector": "Financial"},
    # Consumer Discretionary (~10)
    {"code": "AMZN", "ticker": "AMZN", "name": "Amazon", "sector": "ConsDisc"},
    {"code": "TSLA", "ticker": "TSLA", "name": "Tesla", "sector": "ConsDisc"},
    {"code": "HD", "ticker": "HD", "name": "Home Depot", "sector": "ConsDisc"},
    {"code": "MCD", "ticker": "MCD", "name": "McDonald's", "sector": "ConsDisc"},
    {"code": "NKE", "ticker": "NKE", "name": "Nike", "sector": "ConsDisc"},
    {"code": "LOW", "ticker": "LOW", "name": "Lowe's", "sector": "ConsDisc"},
    {"code": "SBUX", "ticker": "SBUX", "name": "Starbucks", "sector": "ConsDisc"},
    {"code": "TJX", "ticker": "TJX", "name": "TJX Companies", "sector": "ConsDisc"},
    {"code": "BKNG", "ticker": "BKNG", "name": "Booking", "sector": "ConsDisc"},
    {"code": "CMG", "ticker": "CMG", "name": "Chipotle", "sector": "ConsDisc"},
    # Communication Services (~6)
    {"code": "GOOGL", "ticker": "GOOGL", "name": "Alphabet", "sector": "CommSvc"},
    {"code": "META", "ticker": "META", "name": "Meta", "sector": "CommSvc"},
    {"code": "NFLX", "ticker": "NFLX", "name": "Netflix", "sector": "CommSvc"},
    {"code": "DIS", "ticker": "DIS", "name": "Walt Disney", "sector": "CommSvc"},
    {"code": "CMCSA", "ticker": "CMCSA", "name": "Comcast", "sector": "CommSvc"},
    {"code": "T", "ticker": "T", "name": "AT&T", "sector": "CommSvc"},
    # Consumer Staples (~8)
    {"code": "PG", "ticker": "PG", "name": "Procter & Gamble", "sector": "ConsStaple"},
    {"code": "COST", "ticker": "COST", "name": "Costco", "sector": "ConsStaple"},
    {"code": "WMT", "ticker": "WMT", "name": "Walmart", "sector": "ConsStaple"},
    {"code": "KO", "ticker": "KO", "name": "Coca-Cola", "sector": "ConsStaple"},
    {"code": "PEP", "ticker": "PEP", "name": "PepsiCo", "sector": "ConsStaple"},
    {"code": "PM", "ticker": "PM", "name": "Philip Morris", "sector": "ConsStaple"},
    {"code": "CL", "ticker": "CL", "name": "Colgate-Palmolive", "sector": "ConsStaple"},
    {"code": "MDLZ", "ticker": "MDLZ", "name": "Mondelez", "sector": "ConsStaple"},
    # Energy (~8)
    {"code": "XOM", "ticker": "XOM", "name": "Exxon Mobil", "sector": "Energy"},
    {"code": "CVX", "ticker": "CVX", "name": "Chevron", "sector": "Energy"},
    {"code": "COP", "ticker": "COP", "name": "ConocoPhillips", "sector": "Energy"},
    {"code": "SLB", "ticker": "SLB", "name": "Schlumberger", "sector": "Energy"},
    {"code": "EOG", "ticker": "EOG", "name": "EOG Resources", "sector": "Energy"},
    {"code": "MPC", "ticker": "MPC", "name": "Marathon Petroleum", "sector": "Energy"},
    {"code": "PSX", "ticker": "PSX", "name": "Phillips 66", "sector": "Energy"},
    {"code": "VLO", "ticker": "VLO", "name": "Valero Energy", "sector": "Energy"},
    # Industrials (~12)
    {"code": "GE", "ticker": "GE", "name": "GE Aerospace", "sector": "Industrial"},
    {"code": "CAT", "ticker": "CAT", "name": "Caterpillar", "sector": "Industrial"},
    {"code": "RTX", "ticker": "RTX", "name": "RTX Corp", "sector": "Industrial"},
    {"code": "UNP", "ticker": "UNP", "name": "Union Pacific", "sector": "Industrial"},
    {"code": "HON", "ticker": "HON", "name": "Honeywell", "sector": "Industrial"},
    {"code": "BA", "ticker": "BA", "name": "Boeing", "sector": "Industrial"},
    {"code": "DE", "ticker": "DE", "name": "Deere & Co", "sector": "Industrial"},
    {"code": "LMT", "ticker": "LMT", "name": "Lockheed Martin", "sector": "Industrial"},
    {"code": "UPS", "ticker": "UPS", "name": "UPS", "sector": "Industrial"},
    {"code": "MMM", "ticker": "MMM", "name": "3M", "sector": "Industrial"},
    {"code": "GD", "ticker": "GD", "name": "General Dynamics", "sector": "Industrial"},
    {"code": "NOC", "ticker": "NOC", "name": "Northrop Grumman", "sector": "Industrial"},
    # Materials (~6)
    {"code": "LIN", "ticker": "LIN", "name": "Linde", "sector": "Materials"},
    {"code": "APD", "ticker": "APD", "name": "Air Products", "sector": "Materials"},
    {"code": "SHW", "ticker": "SHW", "name": "Sherwin-Williams", "sector": "Materials"},
    {"code": "FCX", "ticker": "FCX", "name": "Freeport-McMoRan", "sector": "Materials"},
    {"code": "NEM", "ticker": "NEM", "name": "Newmont", "sector": "Materials"},
    {"code": "ECL", "ticker": "ECL", "name": "Ecolab", "sector": "Materials"},
    # Utilities (~4)
    {"code": "NEE", "ticker": "NEE", "name": "NextEra Energy", "sector": "Utilities"},
    {"code": "DUK", "ticker": "DUK", "name": "Duke Energy", "sector": "Utilities"},
    {"code": "SO", "ticker": "SO", "name": "Southern Company", "sector": "Utilities"},
    {"code": "D", "ticker": "D", "name": "Dominion Energy", "sector": "Utilities"},
    # Real Estate (~4)
    {"code": "PLD", "ticker": "PLD", "name": "Prologis", "sector": "RealEstate"},
    {"code": "AMT", "ticker": "AMT", "name": "American Tower", "sector": "RealEstate"},
    {"code": "CCI", "ticker": "CCI", "name": "Crown Castle", "sector": "RealEstate"},
    {"code": "EQIX", "ticker": "EQIX", "name": "Equinix", "sector": "RealEstate"},
    # ── ETF (Fixed Pair Arbitrage v5용) ──
    {"code": "SPY", "ticker": "SPY", "name": "SPDR S&P 500", "sector": "ETF"},
    {"code": "IVV", "ticker": "IVV", "name": "iShares S&P 500", "sector": "ETF"},
    {"code": "VOO", "ticker": "VOO", "name": "Vanguard S&P 500", "sector": "ETF"},
    {"code": "SMH", "ticker": "SMH", "name": "VanEck Semiconductor", "sector": "ETF"},
    {"code": "SOXX", "ticker": "SOXX", "name": "iShares Semiconductor", "sector": "ETF"},
]

# ── NASDAQ 100 구성종목 (~70 종목) ──
# 실제 NDX 구성종목 기반, SP500과 일부 중복 있음
NDX_FULL: List[Dict[str, str]] = [
    # Mega-cap Tech
    {"code": "AAPL", "ticker": "AAPL", "name": "Apple", "sector": "Tech"},
    {"code": "MSFT", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
    {"code": "NVDA", "ticker": "NVDA", "name": "NVIDIA", "sector": "Semicon"},
    {"code": "AMZN", "ticker": "AMZN", "name": "Amazon", "sector": "ConsDisc"},
    {"code": "META", "ticker": "META", "name": "Meta", "sector": "CommSvc"},
    {"code": "GOOGL", "ticker": "GOOGL", "name": "Alphabet", "sector": "CommSvc"},
    {"code": "AVGO", "ticker": "AVGO", "name": "Broadcom", "sector": "Semicon"},
    {"code": "TSLA", "ticker": "TSLA", "name": "Tesla", "sector": "ConsDisc"},
    {"code": "COST", "ticker": "COST", "name": "Costco", "sector": "ConsStaple"},
    {"code": "NFLX", "ticker": "NFLX", "name": "Netflix", "sector": "CommSvc"},
    # Software & Services
    {"code": "ADBE", "ticker": "ADBE", "name": "Adobe", "sector": "Tech"},
    {"code": "INTU", "ticker": "INTU", "name": "Intuit", "sector": "Tech"},
    {"code": "PANW", "ticker": "PANW", "name": "Palo Alto Networks", "sector": "Tech"},
    {"code": "SNPS", "ticker": "SNPS", "name": "Synopsys", "sector": "Tech"},
    {"code": "CDNS", "ticker": "CDNS", "name": "Cadence Design", "sector": "Tech"},
    {"code": "FTNT", "ticker": "FTNT", "name": "Fortinet", "sector": "Tech"},
    {"code": "ADSK", "ticker": "ADSK", "name": "Autodesk", "sector": "Tech"},
    {"code": "ADP", "ticker": "ADP", "name": "ADP", "sector": "Tech"},
    {"code": "WDAY", "ticker": "WDAY", "name": "Workday", "sector": "Tech"},
    {"code": "CRWD", "ticker": "CRWD", "name": "CrowdStrike", "sector": "Tech"},
    {"code": "PAYX", "ticker": "PAYX", "name": "Paychex", "sector": "Tech"},
    {"code": "CTSH", "ticker": "CTSH", "name": "Cognizant", "sector": "Tech"},
    {"code": "CDW", "ticker": "CDW", "name": "CDW Corp", "sector": "Tech"},
    {"code": "ANSS", "ticker": "ANSS", "name": "ANSYS", "sector": "Tech"},
    {"code": "TTD", "ticker": "TTD", "name": "The Trade Desk", "sector": "Tech"},
    {"code": "ZS", "ticker": "ZS", "name": "Zscaler", "sector": "Tech"},
    {"code": "TEAM", "ticker": "TEAM", "name": "Atlassian", "sector": "Tech"},
    {"code": "DDOG", "ticker": "DDOG", "name": "Datadog", "sector": "Tech"},
    # Semiconductors
    {"code": "AMD", "ticker": "AMD", "name": "AMD", "sector": "Semicon"},
    {"code": "QCOM", "ticker": "QCOM", "name": "Qualcomm", "sector": "Semicon"},
    {"code": "TXN", "ticker": "TXN", "name": "Texas Instruments", "sector": "Semicon"},
    {"code": "INTC", "ticker": "INTC", "name": "Intel", "sector": "Semicon"},
    {"code": "AMAT", "ticker": "AMAT", "name": "Applied Materials", "sector": "Semicon"},
    {"code": "MU", "ticker": "MU", "name": "Micron", "sector": "Semicon"},
    {"code": "LRCX", "ticker": "LRCX", "name": "Lam Research", "sector": "Semicon"},
    {"code": "KLAC", "ticker": "KLAC", "name": "KLA Corp", "sector": "Semicon"},
    {"code": "MRVL", "ticker": "MRVL", "name": "Marvell Tech", "sector": "Semicon"},
    {"code": "NXPI", "ticker": "NXPI", "name": "NXP Semi", "sector": "Semicon"},
    {"code": "ON", "ticker": "ON", "name": "ON Semiconductor", "sector": "Semicon"},
    # Healthcare & Biotech
    {"code": "ISRG", "ticker": "ISRG", "name": "Intuitive Surgical", "sector": "Health"},
    {"code": "REGN", "ticker": "REGN", "name": "Regeneron", "sector": "Health"},
    {"code": "VRTX", "ticker": "VRTX", "name": "Vertex Pharma", "sector": "Health"},
    {"code": "GILD", "ticker": "GILD", "name": "Gilead Sciences", "sector": "Health"},
    {"code": "DXCM", "ticker": "DXCM", "name": "DexCom", "sector": "Health"},
    {"code": "GEHC", "ticker": "GEHC", "name": "GE Healthcare", "sector": "Health"},
    {"code": "BIIB", "ticker": "BIIB", "name": "Biogen", "sector": "Health"},
    {"code": "ILMN", "ticker": "ILMN", "name": "Illumina", "sector": "Health"},
    # Consumer Discretionary
    {"code": "BKNG", "ticker": "BKNG", "name": "Booking", "sector": "ConsDisc"},
    {"code": "MELI", "ticker": "MELI", "name": "MercadoLibre", "sector": "ConsDisc"},
    {"code": "ORLY", "ticker": "ORLY", "name": "O'Reilly Auto", "sector": "ConsDisc"},
    {"code": "MAR", "ticker": "MAR", "name": "Marriott", "sector": "ConsDisc"},
    {"code": "PDD", "ticker": "PDD", "name": "PDD Holdings", "sector": "ConsDisc"},
    {"code": "ROST", "ticker": "ROST", "name": "Ross Stores", "sector": "ConsDisc"},
    {"code": "LULU", "ticker": "LULU", "name": "Lululemon", "sector": "ConsDisc"},
    # Consumer Staples
    {"code": "MDLZ", "ticker": "MDLZ", "name": "Mondelez", "sector": "ConsStaple"},
    {"code": "MNST", "ticker": "MNST", "name": "Monster Beverage", "sector": "ConsStaple"},
    {"code": "KDP", "ticker": "KDP", "name": "Keurig Dr Pepper", "sector": "ConsStaple"},
    {"code": "KHC", "ticker": "KHC", "name": "Kraft Heinz", "sector": "ConsStaple"},
    # Industrials
    {"code": "CSX", "ticker": "CSX", "name": "CSX Corp", "sector": "Industrial"},
    {"code": "PCAR", "ticker": "PCAR", "name": "PACCAR", "sector": "Industrial"},
    {"code": "CPRT", "ticker": "CPRT", "name": "Copart", "sector": "Industrial"},
    {"code": "ROP", "ticker": "ROP", "name": "Roper Technologies", "sector": "Industrial"},
    {"code": "CTAS", "ticker": "CTAS", "name": "Cintas", "sector": "Industrial"},
    {"code": "ODFL", "ticker": "ODFL", "name": "Old Dominion Freight", "sector": "Industrial"},
    {"code": "FAST", "ticker": "FAST", "name": "Fastenal", "sector": "Industrial"},
    {"code": "VRSK", "ticker": "VRSK", "name": "Verisk Analytics", "sector": "Industrial"},
    # Financial
    {"code": "PYPL", "ticker": "PYPL", "name": "PayPal", "sector": "Financial"},
    # Communication & Media
    {"code": "EA", "ticker": "EA", "name": "Electronic Arts", "sector": "CommSvc"},
    {"code": "WBD", "ticker": "WBD", "name": "Warner Bros", "sector": "CommSvc"},
    # Utilities
    {"code": "EXC", "ticker": "EXC", "name": "Exelon", "sector": "Utilities"},
    # ── ETF (Fixed Pair Arbitrage v5용) ──
    {"code": "QQQ", "ticker": "QQQ", "name": "Invesco QQQ", "sector": "ETF"},
    {"code": "QQQM", "ticker": "QQQM", "name": "Invesco Nasdaq 100 Mini", "sector": "ETF"},
]

# ── KOSPI 200 구성종목 (시총 상위 ~100종목, 전체 tactical) ──
# watchlists.py의 KOSPI_WATCHLIST를 재사용하여 일관성 유지
from simulation.watchlists import KOSPI_WATCHLIST as _KOSPI_WL
KOSPI200_FULL: List[Dict[str, str]] = _KOSPI_WL


# ── 유니버스 설정 레지스트리 ──
UNIVERSE_CONFIG: Dict[str, Dict] = {
    "sp500_full": {
        "constituents": SP500_FULL,
        "market_id": "sp500",
        "top_n": 15,
        "label": "S&P 500 Full Universe",
    },
    "ndx_full": {
        "constituents": NDX_FULL,
        "market_id": "ndx",
        "top_n": 15,
        "label": "NASDAQ 100 Full Universe",
    },
    "kospi_full": {
        "constituents": KOSPI200_FULL,
        "market_id": "kospi",
        "top_n": 10,
        "label": "KOSPI 200 Full Universe",
    },
    # ── 시가총액 상위 60종목 유니버스 (기존 리스트는 시총 순 정렬) ──
    "sp500_top60": {
        "constituents": SP500_FULL[:60],
        "market_id": "sp500",
        "top_n": 10,
        "label": "S&P 500 Top 60 → 10",
    },
    "ndx_top60": {
        "constituents": NDX_FULL[:60],
        "market_id": "ndx",
        "top_n": 10,
        "label": "NASDAQ 100 Top 60 → 10",
    },
    "kospi_top60": {
        "constituents": KOSPI200_FULL[:60],
        "market_id": "kospi",
        "top_n": 10,
        "label": "KOSPI 200 Top 60 → 10",
    },
}


# ── 마켓별 최적 전략 설정 (백테스트 검증 완료 2024-2025) ──
# KOSPI: Top60 + 고정사이징 + ES2 제거 → Sharpe 0.19→0.93, 수익률 0.12%→11.84%
# SP500: Top60 + 고정사이징 + ES2 제거 → MDD -13.5%→-9.0%, Sharpe 유사
# NDX: 기존 전략 유지 → 모든 대안 열위 (Baseline Sharpe 0.87 압도)
OPTIMAL_STRATEGY_CONFIG: Dict[str, Dict] = {
    "kospi": {
        "universe": "kospi_top60",
        "top_n": 10,
        "initial_capital": 30_000_000,
        "fixed_amount_per_stock": 0,  # ATR + Kelly 동적 사이징 활성화
        "disable_es2": True,
        "label": "KOSPI Top60 동적사이징",
    },
    "sp500": {
        "universe": "sp500_top60",
        "top_n": 10,
        "initial_capital": 30_000,
        "fixed_amount_per_stock": 0,  # ATR + Kelly 동적 사이징 활성화
        "disable_es2": True,
        "label": "SP500 Top60 동적사이징",
    },
    "ndx": {
        "universe": "ndx_full",
        "top_n": 15,
        "initial_capital": 100_000,
        "fixed_amount_per_stock": 0,  # ATR 사이징 유지
        "disable_es2": False,  # ES2 유지
        "label": "NDX 기존전략 유지 (검증완료)",
    },
}


def _compute_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """순수 pandas로 ADX(Average Directional Index)를 계산한다.

    Args:
        high: 고가 시리즈
        low: 저가 시리즈
        close: 종가 시리즈
        period: ADX 계산 기간 (기본 14)

    Returns:
        ADX 값의 pandas Series
    """
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)

    # +DM과 -DM 중 더 큰 방향만 남기고 나머지는 0으로
    mask_plus = plus_dm <= minus_dm
    mask_minus = minus_dm <= plus_dm
    plus_dm = plus_dm.copy()
    minus_dm = minus_dm.copy()
    plus_dm[mask_plus] = 0
    minus_dm[mask_minus] = 0

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR, +DI, -DI
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))

    # DX -> ADX
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx = dx.rolling(window=period).mean()
    return adx


class UniverseScanner:
    """전체 유니버스 종목을 스캔하여 모멘텀 상위 종목을 선별한다.

    Pre-filter 조건:
        1. close > MA200 (장기 상승 추세)
        2. ADX > 15 (최소한의 추세 존재)
        3. 20일 평균 거래량 > 100,000 (유동성 확보)

    Momentum Score 구성:
        - 60%: 6개월(126거래일) 수익률
        - 25%: MA50 기울기(최근 5일)
        - 15%: 거래량 트렌드(5일 vs 20일 평균)

    Args:
        constituents: 스캔 대상 종목 리스트
        top_n: 선별할 상위 종목 수 (기본 15)
        min_data_days: 최소 필요 데이터 일수 (기본 220, MA200 + 여유분)
    """

    def __init__(
        self,
        constituents: List[Dict[str, str]],
        top_n: int = 15,
        min_data_days: int = 220,
    ):
        self.constituents = constituents
        self.top_n = top_n
        self.min_data_days = min_data_days

    def scan(
        self,
        ohlcv_map: Dict[str, pd.DataFrame],
        current_date: str,
    ) -> List[Dict[str, str]]:
        """프리필터 + 모멘텀 랭킹을 적용하여 top_n 워치리스트를 반환한다.

        Args:
            ohlcv_map: {종목코드: OHLCV DataFrame} 맵.
                       DataFrame은 'date', 'open', 'high', 'low', 'close', 'volume'
                       컬럼을 포함해야 한다.
            current_date: 스캔 기준일 (예: "2025-01-15")

        Returns:
            모멘텀 점수 상위 top_n 종목의 Dict 리스트.
            각 Dict는 {"code", "ticker", "name", "sector"} 형태.
        """
        scored: List[tuple] = []  # (score, stock_dict)

        for stock in self.constituents:

            code = stock["code"]
            df = ohlcv_map.get(code)
            if df is None or df.empty:
                continue

            # current_date까지만 사용
            df_slice = df[df["date"] <= current_date].copy()
            if len(df_slice) < self.min_data_days:
                continue

            if not self._passes_prefilter(df_slice):
                continue

            score = self._compute_momentum_score(df_slice)
            if score is not None:
                scored.append((score, stock))

        # 점수 내림차순 정렬, 상위 top_n
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[: self.top_n]]

    def scan_with_recommendations(
        self,
        ohlcv_map: Dict[str, pd.DataFrame],
        current_date: str,
        active_positions: Optional[Dict[str, object]] = None,
    ) -> Dict:
        """scan() 결과에 현재 포지션을 비교하여 BUY/SELL/HOLD를 분류한다.

        웹 대시보드용. 모든 종목의 모멘텀 점수를 포함한다.

        Args:
            ohlcv_map: {종목코드: OHLCV DataFrame} 맵
            current_date: 스캔 기준일
            active_positions: {종목코드: position 객체} 맵.
                              position 객체는 pnl_pct, days_held, current_price
                              속성을 가져야 한다.

        Returns:
            {
                "buy": [...],           # top_n에 신규 진입 추천
                "hold": [...],          # top_n에 유지 중인 포지션
                "sell": [...],          # top_n에서 탈락한 포지션
                "all_scores": {...},    # {code: score} 전체 점수
                "scan_date": str,
                "total_scanned": int,
                "passed_prefilter": int,
            }
        """
        if active_positions is None:
            active_positions = {}

        all_scores: Dict[str, float] = {}
        passed_prefilter = 0
        scored_stocks: List[tuple] = []

        for stock in self.constituents:

            code = stock["code"]
            df = ohlcv_map.get(code)
            if df is None or df.empty:
                continue

            df_slice = df[df["date"] <= current_date].copy()
            if len(df_slice) < self.min_data_days:
                continue

            if not self._passes_prefilter(df_slice):
                continue
            passed_prefilter += 1

            score = self._compute_momentum_score(df_slice)
            if score is not None:
                all_scores[code] = round(score, 1)
                scored_stocks.append((score, stock, df_slice))

        # 상위 top_n 선별
        scored_stocks.sort(key=lambda x: x[0], reverse=True)
        top_codes = {s[1]["code"] for s in scored_stocks[: self.top_n]}
        active_codes = set(active_positions.keys()) if active_positions else set()

        # BUY: top_n에 있고 현재 보유하지 않은 종목
        buy_list = []
        for score, stock, df_slice in scored_stocks[: self.top_n]:
            if stock["code"] not in active_codes:
                last_close = float(df_slice.iloc[-1]["close"])
                # 6개월 수익률
                idx_6m = max(0, len(df_slice) - 126)
                ret_6m = (last_close - float(df_slice.iloc[idx_6m]["close"])) / float(
                    df_slice.iloc[idx_6m]["close"]
                )
                buy_list.append(
                    {
                        "rank": len(buy_list) + 1,
                        "code": stock["code"],
                        "name": stock["name"],
                        "sector": stock.get("sector", ""),
                        "score": round(score, 1),
                        "price": round(last_close, 2),
                        "return_6m": f"{ret_6m:+.1%}",
                        "action": "BUY",
                    }
                )

        # HOLD: top_n에 있고 현재 보유 중인 종목
        hold_list = []
        for score, stock, df_slice in scored_stocks[: self.top_n]:
            if stock["code"] in active_codes:
                pos = active_positions[stock["code"]]
                last_close = float(df_slice.iloc[-1]["close"])
                hold_list.append(
                    {
                        "rank": len(hold_list) + 1,
                        "code": stock["code"],
                        "name": stock["name"],
                        "sector": stock.get("sector", ""),
                        "score": round(score, 1),
                        "price": round(last_close, 2),
                        "pnl_pct": getattr(pos, "pnl_pct", 0),
                        "days_held": getattr(pos, "days_held", 0),
                        "action": "HOLD",
                    }
                )

        # SELL: 현재 보유 중이지만 top_n에서 탈락한 종목
        sell_list = []
        for code in active_codes:
            if code not in top_codes:
                pos = active_positions[code]
                stock_info = next(
                    (s for s in self.constituents if s["code"] == code), None
                )
                name = stock_info["name"] if stock_info else code
                sector = stock_info.get("sector", "") if stock_info else ""
                score_val = all_scores.get(code, 0)
                sell_list.append(
                    {
                        "rank": len(sell_list) + 1,
                        "code": code,
                        "name": name,
                        "sector": sector,
                        "score": score_val,
                        "price": getattr(pos, "current_price", 0),
                        "pnl_pct": getattr(pos, "pnl_pct", 0),
                        "reason": "모멘텀 탈락",
                        "action": "SELL",
                    }
                )

        return {
            "buy": buy_list[:10],
            "hold": hold_list[:10],
            "sell": sell_list[:10],
            "all_scores": all_scores,
            "scan_date": current_date,
            "total_scanned": len(self.constituents),
            "passed_prefilter": passed_prefilter,
        }

    def _passes_prefilter(self, df: pd.DataFrame) -> bool:
        """프리필터 3가지 조건을 모두 충족하는지 검사한다.

        조건:
            1. 현재 종가 > MA200 (장기 상승 추세 확인)
            2. ADX(14) > 15 (최소한의 추세 강도 확인)
            3. 20일 평균 거래량 > 100,000 (유동성 확보)

        Args:
            df: OHLCV DataFrame (최소 200행 이상)

        Returns:
            3가지 조건 모두 충족 시 True
        """
        if len(df) < 200:
            return False

        close = df["close"].astype(float)
        ma200 = close.rolling(200).mean().iloc[-1]
        if pd.isna(ma200) or close.iloc[-1] <= ma200:
            return False

        # ADX > 15
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        adx = _compute_adx(high, low, close, period=14)
        last_adx = adx.iloc[-1]
        if pd.isna(last_adx) or last_adx <= 15:
            return False

        # 20일 평균 거래량 > 100K
        vol = df["volume"].astype(float)
        avg_vol_20 = vol.tail(20).mean()
        if avg_vol_20 <= 100_000:
            return False

        return True

    def _compute_momentum_score(self, df: pd.DataFrame) -> Optional[float]:
        """모멘텀 종합 점수를 계산한다.

        구성 요소:
            1. 6개월(126거래일) 수익률 -> 0-100 스케일 (가중치 60%)
               -50% ~ +100% 범위를 0 ~ 100으로 매핑
            2. MA50 기울기(최근 5일) -> 0-100 스케일 (가중치 25%)
               -5% ~ +5% 범위를 0 ~ 100으로 매핑
            3. 거래량 트렌드(5일 평균 / 20일 평균) -> 0-100 스케일 (가중치 15%)
               0.5 ~ 2.0 범위를 0 ~ 100으로 매핑

        Args:
            df: OHLCV DataFrame (최소 126행 이상)

        Returns:
            0~100 범위의 종합 모멘텀 점수. 계산 불가 시 None.
        """
        close = df["close"].astype(float)
        volume = df["volume"].astype(float)

        # 1. 6개월(126거래일) 수익률 (0-100 스케일)
        if len(close) < 126:
            return None
        ret_6m = (close.iloc[-1] - close.iloc[-126]) / close.iloc[-126]
        # -50%~+100% -> 0~100 스케일
        ret_score = max(0, min(100, (ret_6m + 0.5) / 1.5 * 100))

        # 2. MA50 기울기 (최근 5일 기울기)
        ma50 = close.rolling(50).mean()
        if len(ma50) < 55 or pd.isna(ma50.iloc[-1]) or pd.isna(ma50.iloc[-5]):
            return None
        ma50_slope = (ma50.iloc[-1] - ma50.iloc[-5]) / ma50.iloc[-5] * 100
        # -5%~+5% -> 0~100 스케일
        slope_score = max(0, min(100, (ma50_slope + 5) / 10 * 100))

        # 3. 거래량 트렌드 (20일 평균 대비 최근 5일)
        avg_vol_20 = volume.tail(20).mean()
        avg_vol_5 = volume.tail(5).mean()
        if avg_vol_20 > 0:
            vol_ratio = avg_vol_5 / avg_vol_20
        else:
            vol_ratio = 1.0
        # 0.5~2.0 -> 0~100 스케일
        vol_score = max(0, min(100, (vol_ratio - 0.5) / 1.5 * 100))

        # 종합: 60% + 25% + 15%
        total = ret_score * 0.6 + slope_score * 0.25 + vol_score * 0.15
        return total
