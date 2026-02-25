"""
SQLite 데이터베이스 연결 관리
문서: ATS-SAD-001 Part B
"""

import os
from sqlalchemy import create_engine
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
        self._session_factory = sessionmaker(bind=self.engine)
        logger.info("Database connected | path=%s", db_path)

    def init_tables(self):
        """모든 테이블을 생성한다 (존재하면 스킵)."""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables initialized")

    def get_session(self) -> Session:
        """새 세션을 반환한다."""
        return self._session_factory()

    def close(self):
        """엔진을 종료한다."""
        self.engine.dispose()
        logger.info("Database connection closed")
