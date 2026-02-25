#!/usr/bin/env python3
"""
백테스트용 OHLCV 샘플 데이터 생성기

KOSPI200 주요 종목의 현실적인 가격 데이터를 생성한다.
실제 시장 데이터가 아닌 시뮬레이션 데이터임에 유의.

Usage:
    python scripts/generate_backtest_data.py
    python scripts/generate_backtest_data.py --output-dir data_store/backtest_data
"""

import argparse
import csv
import math
import os
import random
import sys

# 종목별 설정: (코드, 이름, 기준가, 일변동성%, 추세drift%)
# 기준가는 2024년 초 실제 시세 참고, 추세는 다양하게 설정
STOCKS = [
    # code, name, base_price, daily_vol%, trend_drift%
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


def load_trading_dates(ref_csv: str) -> list[str]:
    """기존 005930.csv에서 거래일 목록을 추출한다."""
    dates = []
    with open(ref_csv, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dates.append(row["date"].strip())
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

    price = base_price
    base_volume = int(base_price * 50)  # 기준 거래량 (가격에 반비례하게 조정)
    base_volume = max(500000, min(base_volume, 30000000))

    # 추세 반전 포인트 (일부 종목에 모멘텀 시그널 발생 유도)
    reversal_day = rng.randint(30, 60)
    has_reversal = rng.random() < 0.5

    for i, date in enumerate(dates):
        # 추세 전환
        if has_reversal and i == reversal_day:
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
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 기존 005930.csv에서 거래일 추출
    ref_csv = os.path.join(output_dir, "005930.csv")
    if not os.path.exists(ref_csv):
        print(f"❌ 기준 파일 없음: {ref_csv}")
        print("   005930.csv가 있어야 거래일을 추출할 수 있습니다.")
        sys.exit(1)

    dates = load_trading_dates(ref_csv)
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

    print(f"\n✅ {generated}종목 생성 완료 (기존 005930 포함 총 {generated + 1}종목)")


if __name__ == "__main__":
    main()
