#!/usr/bin/env python3
"""
백테스트용 OHLCV 샘플 데이터 생성기

KOSPI200 주요 종목의 현실적인 가격 데이터를 생성한다.
실제 시장 데이터가 아닌 시뮬레이션 데이터임에 유의.

Usage:
    python scripts/generate_backtest_data.py
    python scripts/generate_backtest_data.py --year 2024
    python scripts/generate_backtest_data.py --start 2024-01-01 --end 2024-12-31
    python scripts/generate_backtest_data.py --output-dir data_store/backtest_data
"""

import argparse
import csv
import math
import os
import random
import sys
from datetime import date, timedelta

# 종목별 설정: (코드, 이름, 기준가, 일변동성%, 추세drift%)
# 기준가는 2024년 초 실제 시세 참고, 추세는 다양하게 설정
STOCKS = [
    # code, name, base_price, daily_vol%, trend_drift%
    ("005930", "삼성전자",        70000, 1.8,  0.05),    # 대장주 완만 상승
    ("000660", "SK하이닉스",     132000, 2.5,  0.15),   # 반도체 강세
    ("373220", "LG에너지솔루션", 420000, 1.8, -0.05),   # 횡보~약세
    ("207940", "삼성바이오로직스", 780000, 1.5,  0.03),  # 완만 상승
    ("005380", "현대차",          185000, 2.0,  0.10),   # 상승 추세
    ("006400", "삼성SDI",        450000, 2.2, -0.08),    # 하락 추세
    ("051910", "LG화학",         480000, 2.0, -0.10),    # 하락 추세
    ("035420", "NAVER",          210000, 2.3,  0.05),    # 완만 상승
    ("000270", "기아",            83000, 2.0,  0.12),    # 상승 추세
    ("005490", "POSCO홀딩스",    380000, 1.8, -0.03),    # 약보합
    ("035720", "카카오",          48000, 2.8, -0.12),    # 하락 추세
    ("068270", "셀트리온",       175000, 2.0,  0.08),    # 상승 추세
    ("028260", "삼성물산",       115000, 1.5,  0.04),    # 완만 상승
    ("105560", "KB금융",          55000, 1.6,  0.10),    # 금융 강세
    ("055550", "신한지주",        38000, 1.5,  0.08),    # 금융 강세
    ("012330", "현대모비스",     230000, 1.8, -0.02),    # 횡보
    ("066570", "LG전자",          95000, 2.0,  0.06),    # 완만 상승
    ("003670", "포스코퓨처엠",   320000, 2.5, -0.15),    # 하락 추세
    ("086790", "하나금융지주",    42000, 1.5,  0.09),    # 금융 강세
    ("096770", "SK이노베이션",   135000, 2.2, -0.06),    # 약세
    ("034730", "SK",             165000, 1.8,  0.02),    # 횡보
    ("015760", "한국전력",        18500, 2.0,  0.00),    # 횡보
    ("003550", "LG",              72000, 1.6,  0.03),    # 완만 상승
    ("032830", "삼성생명",        68000, 1.4,  0.05),    # 완만 상승
    ("017670", "SK텔레콤",        52000, 1.2,  0.04),    # 안정적 상승
    ("030200", "KT",              33000, 1.3,  0.02),    # 횡보
    ("009150", "삼성전기",       140000, 2.2,  0.07),    # 상승 추세
    ("010130", "고려아연",       520000, 1.8, -0.04),    # 약보합
    ("033780", "KT&G",            88000, 1.0,  0.03),    # 안정적
    ("018260", "삼성에스디에스", 155000, 1.5,  0.05),    # 완만 상승
]


def generate_trading_dates(start: date, end: date) -> list[str]:
    """한국 주식시장 거래일을 생성한다 (주말 + 공휴일 제외).

    공휴일은 대한민국 법정공휴일 기준. 대체공휴일은 간소화하여 적용.
    """
    # 한국 법정공휴일 (연도별 고정일 + 음력 명절은 근사치 사용)
    # 실제 운영 시에는 KRX 휴장일 캘린더를 사용해야 함
    holidays_by_year = {
        2024: [
            date(2024, 1, 1),   # 신정
            date(2024, 2, 9),   # 설날 연휴
            date(2024, 2, 10),  # 설날
            date(2024, 2, 11),  # 설날 연휴
            date(2024, 2, 12),  # 대체공휴일
            date(2024, 3, 1),   # 삼일절
            date(2024, 4, 10),  # 총선
            date(2024, 5, 1),   # 근로자의 날
            date(2024, 5, 5),   # 어린이날
            date(2024, 5, 6),   # 대체공휴일
            date(2024, 5, 15),  # 부처님오신날
            date(2024, 6, 6),   # 현충일
            date(2024, 8, 15),  # 광복절
            date(2024, 9, 16),  # 추석 연휴
            date(2024, 9, 17),  # 추석
            date(2024, 9, 18),  # 추석 연휴
            date(2024, 10, 1),  # 국군의 날
            date(2024, 10, 3),  # 개천절
            date(2024, 10, 9),  # 한글날
            date(2024, 12, 25), # 크리스마스
            date(2024, 12, 31), # 연말 휴장
        ],
        2025: [
            date(2025, 1, 1),   # 신정
            date(2025, 1, 28),  # 설날 연휴
            date(2025, 1, 29),  # 설날
            date(2025, 1, 30),  # 설날 연휴
            date(2025, 3, 1),   # 삼일절
            date(2025, 3, 3),   # 대체공휴일
            date(2025, 5, 1),   # 근로자의 날
            date(2025, 5, 5),   # 어린이날/부처님오신날
            date(2025, 5, 6),   # 대체공휴일
            date(2025, 6, 6),   # 현충일
            date(2025, 8, 15),  # 광복절
            date(2025, 10, 3),  # 개천절
            date(2025, 10, 5),  # 추석 연휴
            date(2025, 10, 6),  # 추석
            date(2025, 10, 7),  # 추석 연휴
            date(2025, 10, 8),  # 대체공휴일
            date(2025, 10, 9),  # 한글날
            date(2025, 12, 25), # 크리스마스
            date(2025, 12, 31), # 연말 휴장
        ],
    }

    # 해당 연도의 공휴일 집합
    holidays = set()
    for year in range(start.year, end.year + 1):
        holidays.update(holidays_by_year.get(year, []))

    dates = []
    d = start
    while d <= end:
        # 주말 제외 (토=5, 일=6)
        if d.weekday() < 5 and d not in holidays:
            dates.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)

    return dates


def tick_round(price: float, base_price: float) -> int:
    """호가 단위에 맞춰 반올림한다 (KRX 호가 단위 간소화)."""
    if base_price >= 500000:
        tick = 1000
    elif base_price >= 100000:
        tick = 500
    elif base_price >= 50000:
        tick = 100
    elif base_price >= 10000:
        tick = 50
    elif base_price >= 5000:
        tick = 10
    else:
        tick = 5
    return int(round(price / tick) * tick)


def generate_ohlcv(
    dates: list[str],
    base_price: float,
    daily_vol_pct: float,
    trend_drift_pct: float,
    seed: int,
) -> list[dict]:
    """현실적인 OHLCV 데이터를 생성한다.

    GBM(Geometric Brownian Motion) 기반으로 가격을 생성하고,
    거래량은 가격 변동성에 비례하여 변동시킨다.
    """
    rng = random.Random(seed)
    rows = []
    n_days = len(dates)

    price = base_price
    base_volume = int(base_price * 50)  # 기준 거래량 (가격에 반비례하게 조정)
    base_volume = max(500000, min(base_volume, 30000000))

    # 추세 반전 포인트: 연간 2~4회 추세 전환 (모멘텀 시그널 발생 유도)
    n_reversals = rng.randint(2, 4)
    reversal_days = set()
    for _ in range(n_reversals):
        reversal_days.add(rng.randint(int(n_days * 0.1), int(n_days * 0.9)))

    for i, date in enumerate(dates):
        # 추세 전환
        if i in reversal_days:
            trend_drift_pct = -trend_drift_pct * rng.uniform(0.5, 1.5)

        # 간헐적 갭 (2% 확률로 큰 갭)
        gap = 0
        if rng.random() < 0.02:
            gap = rng.gauss(0, daily_vol_pct * 2) / 100

        # GBM 일일 수익률
        drift = trend_drift_pct / 100
        vol = daily_vol_pct / 100
        daily_return = drift + vol * rng.gauss(0, 1) + gap

        close_price = price * (1 + daily_return)

        # 일중 변동 시뮬레이션
        intraday_range = abs(rng.gauss(0, vol * 0.7))
        high_ext = rng.uniform(0.3, 0.7) * intraday_range
        low_ext = rng.uniform(0.3, 0.7) * intraday_range

        open_price = price * (1 + rng.gauss(0, vol * 0.3) + gap)
        high_price = max(open_price, close_price) * (1 + high_ext)
        low_price = min(open_price, close_price) * (1 - low_ext)

        # 호가 단위 정리
        o = tick_round(open_price, base_price)
        h = tick_round(high_price, base_price)
        l = tick_round(low_price, base_price)
        c = tick_round(close_price, base_price)

        # high >= max(open, close), low <= min(open, close)
        h = max(h, o, c)
        l = min(l, o, c)

        # 거래량: 변동성 클수록 거래량 증가
        vol_mult = 1 + abs(daily_return) * 20 + rng.uniform(-0.2, 0.2)
        # 월요일/금요일 효과
        day_of_week_effect = 1.0
        if i % 5 == 0:
            day_of_week_effect = 1.15  # 월요일
        elif i % 5 == 4:
            day_of_week_effect = 0.9   # 금요일

        volume = int(base_volume * vol_mult * day_of_week_effect)
        volume = max(100000, volume)

        rows.append({
            "date": date,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": volume,
        })

        price = close_price  # 다음 날 기준가

    return rows


def main():
    parser = argparse.ArgumentParser(description="백테스트용 OHLCV 데이터 생성")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "data_store", "backtest_data"),
        help="CSV 출력 디렉토리",
    )
    parser.add_argument("--year", type=int, default=2024, help="생성 연도 (default: 2024)")
    parser.add_argument("--start", type=str, help="시작일 (YYYY-MM-DD), --year보다 우선")
    parser.add_argument("--end", type=str, help="종료일 (YYYY-MM-DD), --year보다 우선")
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 거래일 생성
    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    else:
        start = date(args.year, 1, 1)
        end = date(args.year, 12, 31)

    dates = generate_trading_dates(start, end)
    print(f"거래일: {len(dates)}일 ({dates[0]} ~ {dates[-1]})")
    print(f"출력: {output_dir}")
    print()

    generated = 0
    for i, (code, name, base_price, vol, drift) in enumerate(STOCKS):
        csv_path = os.path.join(output_dir, f"{code}.csv")

        rows = generate_ohlcv(
            dates=dates,
            base_price=base_price,
            daily_vol_pct=vol,
            trend_drift_pct=drift,
            seed=hash(code) & 0xFFFFFFFF,
        )

        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume"])
            writer.writeheader()
            writer.writerows(rows)

        first = rows[0]["close"]
        last = rows[-1]["close"]
        ret = (last - first) / first * 100
        print(f"  {code} {name:14s} | {first:>10,} → {last:>10,} ({ret:+.1f}%) | {csv_path}")
        generated += 1

    print(f"\n✅ {generated}종목 생성 완료")


if __name__ == "__main__":
    main()
