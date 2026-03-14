"""
ATS 로깅 유틸리티
"""

import logging
import sys


def setup_logger(log_dir: str = "data_store/logs", level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        stream=sys.stdout,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ats.{name}")
