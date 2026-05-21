"""
data/config_manager.py 단위 테스트
TC-CFG-001 ~ TC-CFG-004: 설정 로드 검증
"""

import os
import pytest
import tempfile

from data.config_manager import ConfigManager


class TestConfigManager:

    def test_load_default_config(self, tmp_path):
        """TC-CFG-001: config.yaml 없을 때 기본값 로드."""
        cm = ConfigManager(
            config_path=str(tmp_path / "nonexistent.yaml"),
            env_path=str(tmp_path / ".env"),
        )
        config = cm.load()

        assert config.strategy.ma_short == 5
        assert config.strategy.ma_long == 20
        assert config.exit.stop_loss_pct == -0.03
        assert config.portfolio.max_positions == 10

    def test_load_yaml_config(self, tmp_path):
        """TC-CFG-002: config.yaml 파라미터가 정상 로드."""
        yaml_content = """
system:
  name: "ATS-Custom"
  log_level: "DEBUG"

strategy:
  ma_short: 10
  ma_long: 30

exit:
  stop_loss_pct: -0.05

portfolio:
  max_positions: 5
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        cm = ConfigManager(
            config_path=str(yaml_file),
            env_path=str(tmp_path / ".env"),
        )
        config = cm.load()

        assert config.system_name == "ATS-Custom"
        assert config.log_level == "DEBUG"
        assert config.strategy.ma_short == 10
        assert config.strategy.ma_long == 30
        assert config.exit.stop_loss_pct == -0.05
        assert config.portfolio.max_positions == 5

    def test_env_variables_loaded(self, tmp_path):
        """TC-CFG-003: .env 파일에서 민감 정보 로드."""
        env_content = """
KIS_APP_KEY=my_test_key
KIS_APP_SECRET=my_test_secret
KIS_ACCOUNT_NO=99999999-01
KIS_IS_PAPER=true
TELEGRAM_BOT_TOKEN=bot_token_123
TELEGRAM_CHAT_ID=chat_456
"""
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)

        cm = ConfigManager(
            config_path=str(tmp_path / "config.yaml"),
            env_path=str(env_file),
        )
        config = cm.load()

        assert config.kis_app_key == "my_test_key"
        assert config.kis_account_no == "99999999-01"
        assert config.kis_is_paper is True
        assert config.telegram_bot_token == "bot_token_123"

    def test_config_property_caches(self, tmp_path):
        """TC-CFG-004: config 프로퍼티가 캐싱."""
        cm = ConfigManager(
            config_path=str(tmp_path / "config.yaml"),
            env_path=str(tmp_path / ".env"),
        )
        c1 = cm.config
        c2 = cm.config
        assert c1 is c2  # 같은 객체
