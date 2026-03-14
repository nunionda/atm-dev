"""
ConfigManager 단위 테스트.

YAML 전체 섹션 로딩, .env 로딩, 타입 검증, 가중치 합계 검증.
"""

import os
import tempfile

import pytest

from data.config_manager import ConfigManager, ATSConfig


class TestConfigManagerLoad:
    """YAML 파일 로딩 테스트."""

    def test_load_defaults_when_no_file(self, tmp_path):
        """config.yaml 미존재 시 기본값 반환."""
        cm = ConfigManager(config_path=str(tmp_path / "missing.yaml"))
        config = cm.load()
        assert isinstance(config, ATSConfig)
        assert config.strategy.ma_short == 5
        assert config.sp500_futures.entry_threshold == 60.0

    def test_load_sp500_futures_section(self, tmp_path):
        """sp500_futures 섹션 로딩."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "sp500_futures:\n"
            "  entry_threshold: 70.0\n"
            "  sl_hard_pct: 0.05\n"
            "  max_holding_days: 30\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.sp500_futures.entry_threshold == 70.0
        assert config.sp500_futures.sl_hard_pct == 0.05
        assert config.sp500_futures.max_holding_days == 30

    def test_load_strategy_section(self, tmp_path):
        """strategy 섹션 로딩 (기존 버그: 미로딩)."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "strategy:\n"
            "  ma_short: 10\n"
            "  ma_long: 50\n"
            "  rsi_period: 21\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.strategy.ma_short == 10
        assert config.strategy.ma_long == 50
        assert config.strategy.rsi_period == 21

    def test_load_exit_section(self, tmp_path):
        """exit 섹션 로딩."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "exit:\n"
            "  stop_loss_pct: -0.10\n"
            "  max_holding_days: 60\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.exit.stop_loss_pct == -0.10
        assert config.exit.max_holding_days == 60

    def test_load_portfolio_section(self, tmp_path):
        """portfolio 섹션 로딩."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "portfolio:\n"
            "  max_positions: 60\n"
            "  max_weight_per_stock: 0.05\n"
            "  min_cash_ratio: 0.70\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.portfolio.max_positions == 60
        assert config.portfolio.max_weight_per_stock == 0.05
        assert config.portfolio.min_cash_ratio == 0.70

    def test_load_risk_section(self, tmp_path):
        """risk 섹션 로딩."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "risk:\n"
            "  daily_loss_limit: -0.03\n"
            "  mdd_limit: -0.10\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.risk.daily_loss_limit == -0.03
        assert config.risk.mdd_limit == -0.10

    def test_load_order_section(self, tmp_path):
        """order 섹션 로딩."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "order:\n"
            "  default_buy_type: MARKET\n"
            "  max_retry: 5\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.order.default_buy_type == "MARKET"
        assert config.order.max_retry == 5

    def test_load_smc_strategy_section(self, tmp_path):
        """smc_strategy 섹션 로딩."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "smc_strategy:\n"
            "  swing_length: 5\n"
            "  entry_threshold: 70\n"
            "  weight_smc: 50\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.smc_strategy.swing_length == 5
        assert config.smc_strategy.entry_threshold == 70.0
        assert config.smc_strategy.weight_smc == 50.0

    def test_load_breakout_retest_section(self, tmp_path):
        """breakout_retest 섹션 로딩."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "breakout_retest:\n"
            "  breakout_threshold: 55\n"
            "  retest_max_bars: 25\n"
            "  choch_exit: false\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.breakout_retest.breakout_threshold == 55.0
        assert config.breakout_retest.retest_max_bars == 25
        assert config.breakout_retest.choch_exit is False

    def test_load_system_log_level(self, tmp_path):
        """system.log_level 로딩."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "system:\n"
            "  log_level: DEBUG\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.log_level == "DEBUG"

    def test_load_multiple_sections(self, tmp_path):
        """다중 섹션 동시 로딩."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "strategy:\n"
            "  ma_short: 10\n"
            "exit:\n"
            "  stop_loss_pct: -0.10\n"
            "portfolio:\n"
            "  max_positions: 60\n"
            "sp500_futures:\n"
            "  entry_threshold: 75.0\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.strategy.ma_short == 10
        assert config.exit.stop_loss_pct == -0.10
        assert config.portfolio.max_positions == 60
        assert config.sp500_futures.entry_threshold == 75.0


class TestTypeCoercion:
    """타입 변환 및 검증 테스트."""

    def test_string_to_int(self, tmp_path):
        """YAML 문자열 → int 변환."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            'strategy:\n'
            '  ma_short: "10"\n'
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.strategy.ma_short == 10
        assert isinstance(config.strategy.ma_short, int)

    def test_string_to_float(self, tmp_path):
        """YAML 문자열 → float 변환."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            'sp500_futures:\n'
            '  entry_threshold: "65.5"\n'
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.sp500_futures.entry_threshold == 65.5
        assert isinstance(config.sp500_futures.entry_threshold, float)

    def test_int_to_float(self, tmp_path):
        """YAML int → float 변환 (흔한 케이스: `bb_std: 2`)."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "sp500_futures:\n"
            "  bb_std: 2\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.sp500_futures.bb_std == 2.0
        assert isinstance(config.sp500_futures.bb_std, float)

    def test_bool_coercion(self, tmp_path):
        """bool 타입 변환."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "breakout_retest:\n"
            "  choch_exit: false\n"
            "  divergence_check: true\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.breakout_retest.choch_exit is False
        assert config.breakout_retest.divergence_check is True

    def test_list_to_tuple(self, tmp_path):
        """YAML list → tuple 변환 (rsi_long_range 등)."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "sp500_futures:\n"
            "  rsi_long_range: [35.0, 70.0]\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert config.sp500_futures.rsi_long_range == (35.0, 70.0)
        assert isinstance(config.sp500_futures.rsi_long_range, tuple)

    def test_invalid_type_keeps_default(self, tmp_path):
        """잘못된 타입은 기본값 유지 (에러 로그)."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "strategy:\n"
            '  ma_short: "not_a_number"\n'
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        # Should keep default because int("not_a_number") raises ValueError
        assert config.strategy.ma_short == 5


class TestUnknownKeys:
    """알 수 없는 키 경고 테스트."""

    def test_unknown_key_warning(self, tmp_path, caplog):
        """알 수 없는 키 경고 로그."""
        import logging
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "sp500_futures:\n"
            "  entry_threshhold: 70.0\n"  # typo: threshhold
        )
        cm = ConfigManager(config_path=str(yaml_file))
        with caplog.at_level(logging.WARNING):
            config = cm.load()
        assert "Unknown config key: entry_threshhold" in caplog.text
        # 기본값 유지
        assert config.sp500_futures.entry_threshold == 60.0


class TestWeightValidation:
    """가중치 합계 검증 테스트."""

    def test_valid_weights_no_warning(self, tmp_path, caplog):
        """정상 가중치 (합계 100) → 경고 없음."""
        import logging
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "sp500_futures:\n"
            "  weight_zscore: 25.0\n"
            "  weight_trend: 25.0\n"
            "  weight_momentum: 25.0\n"
            "  weight_volume: 25.0\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        with caplog.at_level(logging.WARNING):
            cm.load()
        assert "4-Layer weights sum" not in caplog.text

    def test_invalid_weights_warning(self, tmp_path, caplog):
        """비정상 가중치 (합계 ≠ 100) → 경고."""
        import logging
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "sp500_futures:\n"
            "  weight_zscore: 30.0\n"
            "  weight_trend: 30.0\n"
            "  weight_momentum: 30.0\n"
            "  weight_volume: 30.0\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        with caplog.at_level(logging.WARNING):
            cm.load()
        assert "4-Layer weights sum to 120.0" in caplog.text


class TestEnvLoading:
    """.env 로딩 테스트."""

    def test_env_vars_loaded(self, tmp_path, monkeypatch):
        """환경변수에서 시크릿 로딩."""
        monkeypatch.setenv("KIS_APP_KEY", "test_key_123")
        monkeypatch.setenv("KIS_APP_SECRET", "test_secret_456")
        monkeypatch.setenv("KIS_ACCOUNT_NO", "12345678")
        monkeypatch.setenv("KIS_IS_PAPER", "false")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot_token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat_123")
        monkeypatch.setenv("DB_PATH", "/tmp/test.db")

        cm = ConfigManager(config_path=str(tmp_path / "missing.yaml"))
        config = cm.load()

        assert config.kis_app_key == "test_key_123"
        assert config.kis_app_secret == "test_secret_456"
        assert config.kis_account_no == "12345678"
        assert config.kis_is_paper is False
        assert config.telegram_bot_token == "bot_token"
        assert config.telegram_chat_id == "chat_123"
        assert config.db_path == "/tmp/test.db"

    def test_env_defaults(self, tmp_path, monkeypatch):
        """환경변수 미설정 시 기본값."""
        for key in ["KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO",
                     "KIS_IS_PAPER", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DB_PATH"]:
            monkeypatch.delenv(key, raising=False)

        cm = ConfigManager(config_path=str(tmp_path / "missing.yaml"))
        config = cm.load()

        assert config.kis_app_key == ""
        assert config.kis_is_paper is True
        assert config.db_path == "data_store/ats.db"


class TestEdgeCases:
    """엣지 케이스 테스트."""

    def test_empty_yaml(self, tmp_path):
        """빈 YAML 파일."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("")
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        assert isinstance(config, ATSConfig)

    def test_non_dict_section_ignored(self, tmp_path):
        """섹션이 dict가 아닌 경우 무시."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "strategy: \"not_a_dict\"\n"
            "sp500_futures:\n"
            "  entry_threshold: 70.0\n"
        )
        cm = ConfigManager(config_path=str(yaml_file))
        config = cm.load()
        # strategy는 기본값 유지, sp500_futures는 정상 로딩
        assert config.strategy.ma_short == 5
        assert config.sp500_futures.entry_threshold == 70.0
