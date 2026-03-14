"""
pytest 공통 설정.

sys.path 에 ats/ 디렉토리를 추가하여 모든 테스트에서
`from data.config_manager import ...` 형태로 임포트 가능.
"""

import os
import sys

# ats/ 디렉토리를 import path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
