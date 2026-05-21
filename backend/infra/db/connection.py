"""
SQLite 데이터베이스 연결 관리
문서: ATS-SAD-001 Part B
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from infra.db.models import Base
from infra.logger import get_logger

logger = get_logger("db")


class Database:
    """SQLite 연결 및 세션 관리."""

    def __init__(self, db_path: str = "data_store/ats.db"):
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        # SQLite FK 제약 활성화
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        self._session_factory = sessionmaker(bind=self.engine)
        logger.info("Database connected | path=%s", db_path)

    def init_tables(self):
        """모든 테이블을 생성한다 (존재하면 스킵). 이후 idempotent 마이그레이션 적용."""
        Base.metadata.create_all(self.engine)
        self._apply_idempotent_migrations()
        logger.info("Database tables initialized")

    def _apply_idempotent_migrations(self):
        """
        ALTER TABLE … ADD COLUMN을 idempotent하게 적용한다.

        SQLite는 ADD COLUMN만 안전하게 지원하므로, 신규 컬럼을
        PRAGMA table_info로 체크 후 없을 때만 추가한다.
        Alembic 없이 라이트한 마이그레이션 전략.
        """
        from sqlalchemy import text

        migrations = {
            # Phase A: Universe rebalance 메타 컬럼 5개
            "universe": [
                ("rebalance_action", "VARCHAR(8)"),
                ("rebalance_score", "FLOAT"),
                ("rebalance_rank", "INTEGER"),
                ("return_6m", "FLOAT"),
                ("last_synced_at", "VARCHAR(30)"),
            ],
        }

        with self.engine.begin() as conn:
            for table_name, columns in migrations.items():
                # 기존 컬럼 목록 조회
                existing = {
                    row[1]
                    for row in conn.execute(text(f"PRAGMA table_info({table_name})"))
                }
                for col_name, col_type in columns:
                    if col_name not in existing:
                        conn.execute(text(
                            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                        ))
                        logger.info("Migration: %s.%s added (%s)", table_name, col_name, col_type)

        # Phase A.2: Universe PK를 (stock_code, market) 복합으로 변환
        self._migrate_universe_pk_composite()

    def _migrate_universe_pk_composite(self):
        """
        멀티마켓(SP500·NDX·KOSPI)에서 같은 ticker가 다른 market에 동시 존재 가능하도록
        Universe.PK를 stock_code 단독 → (stock_code, market) 복합으로 변환.

        SQLite는 ALTER TABLE로 PK 변경 불가 → CREATE_NEW → COPY → DROP_OLD → RENAME 패턴.
        Idempotent — 이미 복합 PK면 skip.
        """
        from sqlalchemy import text

        with self.engine.begin() as conn:
            # PK 컬럼 조회 (pk>0 이 PK)
            pk_cols = sorted(
                (row[1], row[5]) for row in conn.execute(text("PRAGMA table_info(universe)"))
                if row[5] > 0
            )
            pk_names = {name for name, _ in pk_cols}

            if pk_names == {"stock_code", "market"}:
                return  # 이미 복합 PK
            if pk_names != {"stock_code"}:
                logger.warning("Universe PK shape unexpected: %s — skipping migration", pk_names)
                return

            logger.info("Migration: converting Universe PK to (stock_code, market)")
            conn.execute(text("""
                CREATE TABLE universe_new (
                    stock_code VARCHAR(10) NOT NULL,
                    market VARCHAR(10) NOT NULL DEFAULT 'KOSPI',
                    stock_name VARCHAR(50) NOT NULL,
                    sector VARCHAR(50),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    updated_at VARCHAR(30) NOT NULL,
                    rebalance_action VARCHAR(8),
                    rebalance_score FLOAT,
                    rebalance_rank INTEGER,
                    return_6m FLOAT,
                    last_synced_at VARCHAR(30),
                    PRIMARY KEY (stock_code, market)
                )
            """))
            # 기존 데이터 복사 (INSERT OR IGNORE: 가상의 중복 row 발생 시 첫 행만 유지)
            conn.execute(text("""
                INSERT OR IGNORE INTO universe_new
                    (stock_code, market, stock_name, sector, is_active, updated_at,
                     rebalance_action, rebalance_score, rebalance_rank, return_6m, last_synced_at)
                SELECT
                    stock_code, market, stock_name, sector, is_active, updated_at,
                    rebalance_action, rebalance_score, rebalance_rank, return_6m, last_synced_at
                FROM universe
            """))
            conn.execute(text("DROP TABLE universe"))
            conn.execute(text("ALTER TABLE universe_new RENAME TO universe"))
            logger.info("Migration: Universe PK conversion complete")

    def get_session(self) -> Session:
        """새 세션을 반환한다."""
        return self._session_factory()

    def close(self):
        """엔진을 종료한다."""
        self.engine.dispose()
        logger.info("Database connection closed")
