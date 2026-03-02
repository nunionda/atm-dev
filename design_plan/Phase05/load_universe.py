#!/usr/bin/env python3
"""
KOSPI200 유니버스 로더
한투 API 또는 수동 CSV에서 유니버스 종목을 DB에 적재한다.

Usage:
    python scripts/load_universe.py              # 샘플 30종목 (빠른 시작)
    python scripts/load_universe.py --full       # KOSPI200 전체 (API 필요)
    python scripts/load_universe.py --csv FILE   # CSV 파일에서 로드
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.config_manager import ConfigManager
from infra.db.connection import Database
from infra.db.repository import Repository
from infra.logger import setup_logger

# KOSPI200 주요 종목 30선 (빠른 시작용)
SAMPLE_UNIVERSE = [
    ("005930", "삼성전자", "전기전자"),
    ("000660", "SK하이닉스", "전기전자"),
    ("373220", "LG에너지솔루션", "전기전자"),
    ("207940", "삼성바이오로직스", "의약품"),
    ("005380", "현대차", "운수장비"),
    ("006400", "삼성SDI", "전기전자"),
    ("051910", "LG화학", "화학"),
    ("035420", "NAVER", "서비스업"),
    ("000270", "기아", "운수장비"),
    ("005490", "POSCO홀딩스", "철강금속"),
    ("035720", "카카오", "서비스업"),
    ("068270", "셀트리온", "의약품"),
    ("028260", "삼성물산", "유통업"),
    ("105560", "KB금융", "은행"),
    ("055550", "신한지주", "은행"),
    ("012330", "현대모비스", "운수장비"),
    ("066570", "LG전자", "전기전자"),
    ("003670", "포스코퓨처엠", "철강금속"),
    ("086790", "하나금융지주", "은행"),
    ("096770", "SK이노베이션", "화학"),
    ("034730", "SK", "기타"),
    ("015760", "한국전력", "전기가스"),
    ("003550", "LG", "기타"),
    ("032830", "삼성생명", "보험"),
    ("017670", "SK텔레콤", "통신"),
    ("030200", "KT", "통신"),
    ("009150", "삼성전기", "전기전자"),
    ("010130", "고려아연", "비금속광물"),
    ("033780", "KT&G", "음식료"),
    ("018260", "삼성에스디에스", "서비스업"),
]


def load_sample(repo: Repository):
    """샘플 30종목을 로드한다."""
    count = 0
    for code, name, sector in SAMPLE_UNIVERSE:
        repo.upsert_universe(code, name, "KOSPI", sector)
        count += 1
    print(f"✅ 샘플 유니버스 {count}종목 로드 완료")


def load_csv(repo: Repository, csv_path: str):
    """CSV 파일에서 유니버스를 로드한다.
    CSV 형식: stock_code,stock_name,sector
    """
    import csv
    count = 0
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("stock_code", "").strip()
            name = row.get("stock_name", "").strip()
            sector = row.get("sector", "").strip()
            if code and name:
                repo.upsert_universe(code, name, "KOSPI", sector)
                count += 1
    print(f"✅ CSV 유니버스 {count}종목 로드 완료 | source={csv_path}")


def load_full_from_api(repo: Repository, config):
    """한투 API에서 KOSPI200 전체 종목을 조회하여 로드한다."""
    from infra.broker.kis_broker import KISBroker
    import time

    broker = KISBroker(
        app_key=config.kis_app_key,
        app_secret=config.kis_app_secret,
        account_no=config.kis_account_no,
        is_paper=config.kis_is_paper,
    )
    broker.authenticate()

    # 샘플 종목 기반으로 시세 조회 가능한 종목만 등록
    # (KOSPI200 전체 목록은 KRX에서 별도 다운로드 필요)
    print("⚠️  한투 API에는 KOSPI200 구성종목 목록 조회 API가 없습니다.")
    print("   KRX 정보데이터시스템(data.krx.co.kr)에서 CSV를 다운로드한 후")
    print("   'python scripts/load_universe.py --csv <파일>' 로 로드하세요.")
    print()
    print("   대안: 샘플 30종목으로 시작합니다.")
    load_sample(repo)


def main():
    parser = argparse.ArgumentParser(description="ATS 유니버스 로더")
    parser.add_argument("--full", action="store_true", help="KOSPI200 전체 (API 조회)")
    parser.add_argument("--csv", type=str, help="CSV 파일 경로")
    args = parser.parse_args()

    cm = ConfigManager()
    config = cm.load()
    setup_logger(level=config.log_level)

    db = Database(db_path=config.db_path)
    db.init_tables()
    repo = Repository(db)

    if args.csv:
        load_csv(repo, args.csv)
    elif args.full:
        load_full_from_api(repo, config)
    else:
        load_sample(repo)

    # 결과 확인
    active = repo.get_active_universe()
    print(f"\n현재 유니버스: {len(active)}종목")
    for u in active[:10]:
        print(f"  {u.stock_code} {u.stock_name:12s} {u.sector or ''}")
    if len(active) > 10:
        print(f"  ... 외 {len(active) - 10}종목")

    db.close()


if __name__ == "__main__":
    main()
