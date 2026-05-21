"""
ATS 로깅 설정
문서: ATS-SAD-001 §15
"""

import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

_logger_initialized = False


def setup_logger(log_dir: str = "data_store/logs", level: str = "INFO") -> logging.Logger:
    """
    구조화된 로거를 설정한다.
    - 콘솔 + 파일 동시 출력
    - 일별 로테이션, 90일 보존
    """
    global _logger_initialized

    logger = logging.getLogger("ats")

    if _logger_initialized:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "[%(asctime)s.%(msecs)03d] [%(levelname)-8s] [%(module)-20s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── 콘솔 핸들러 ──
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ── 파일 핸들러 (일별 로테이션) ──
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"ats_{today}.log")

    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=90,  # 90일 보존
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    _logger_initialized = True
    logger.info("Logger initialized | level=%s | file=%s", level, log_file)
    return logger


def get_logger(module_name: str = "ats") -> logging.Logger:
    """모듈별 로거를 반환한다."""
    return logging.getLogger(f"ats.{module_name}")
