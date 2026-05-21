"""
S&P500 선물 전략 Phase 2-4 테스트.

Market Regime, EV Engine, Dynamic Kelly, 연속손절 정지.
"""

import numpy as np
import pandas as pd
import pytest

from data.config_manager import ATSConfig, SP500FuturesConfig
from strategy.sp500_futures import SP500FuturesStrategy


def _make_strategy(overrides: dict = None) -> SP500FuturesStrategy:
    """테스트용 전략 인스턴스 생성."""
    config = ATSConfig()
    if overrides:
        for k, v in overrides.items():
            setattr(config.sp500_futures, k, v)
    return SP500FuturesStrategy(config)


def _make_df(n: int = 250, trend: str = "bull") -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성."""
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    if trend == "bull":
        close = np.linspace(4800, 5500, n) + np.random.randn(n) * 5
    elif trend == "bear":
        close = np.linspace(5500, 4800, n) + np.random.randn(n) * 5
    else:
        close = np.full(n, 5100.0) + np.random.randn(n) * 20

    df = pd.DataFrame({
        "open": close - 5,
        "high": close + 10,
        "low": close - 10,
        "close": close,
        "volume": np.random.randint(50000, 200000, n),
    }, index=dates)
    return df


# ══════════════════════════════════════════
# Phase 1A: IndexError 방어
# ══════════════════════════════════════════


class TestScoreFunctionGuards:
    """스코어링 함수 짧은 데이터 방어 테스트."""

    def test_score_momentum_short_df(self):
        """len(df)<2 → (0.0, [])."""
        strategy = _make_strategy()
        df = pd.DataFrame({"close": [5000.0]})
        score, signals = strategy._score_momentum(df, is_long=True)
        assert score == 0.0
        assert signals == []

    def test_score_zscore_empty(self):
        """빈 df → (0.0, [])."""
        strategy = _make_strategy()
        df = pd.DataFrame()
        score, signals = strategy._score_zscore(df, is_long=True)
        assert score == 0.0
        assert signals == []

    def test_score_trend_short_df(self):
        """len(df)<1 → (0.0, [])."""
        strategy = _make_strategy()
        df = pd.DataFrame()
        score, signals = strategy._score_trend(df, is_long=True)
        assert score == 0.0
        assert signals == []

    def test_score_volume_short_df(self):
        """len(df)<1 → (0.0, [])."""
        strategy = _make_strategy()
        df = pd.DataFrame()
        score, signals = strategy._score_volume(df, is_long=True)
        assert score == 0.0
        assert signals == []


# ══════════════════════════════════════════
# Phase 2: Market Regime
# ══════════════════════════════════════════


class TestMarketRegime:
    """Market Regime 판단 테스트."""

    def test_regime_bull(self):
        """Price>MA200 + MA200 상승 + EMA 정배열 → BULL."""
        strategy = _make_strategy()
        df = _make_df(250, "bull")
        df = strategy.calculate_indicators(df)
        regime = strategy._determine_market_regime(df)
        assert regime == "BULL"

    def test_regime_bear(self):
        """Price<MA200 + MA200 하락 + EMA 역배열 → BEAR."""
        strategy = _make_strategy()
        df = _make_df(250, "bear")
        df = strategy.calculate_indicators(df)
        regime = strategy._determine_market_regime(df)
        assert regime == "BEAR"

    def test_regime_short_data(self):
        """데이터 부족 → NEUTRAL."""
        strategy = _make_strategy()
        df = pd.DataFrame({"close": [5000.0], "ma_trend": [5000.0],
                           "ema_fast": [5000.0], "ema_mid": [5000.0], "ema_slow": [5000.0]})
        regime = strategy._determine_market_regime(df)
        assert regime == "NEUTRAL"

    def test_regime_threshold_adjust(self):
        """BEAR 시 entry_threshold → regime_bear_entry_threshold."""
        strategy = _make_strategy({
            "regime_bear_entry_threshold": 70.0,
            "entry_threshold": 60.0,
        })
        assert strategy.fc.regime_bear_entry_threshold == 70.0
        assert strategy.fc.entry_threshold == 60.0


# ══════════════════════════════════════════
# Phase 3: EV Engine + Dynamic Kelly
# ══════════════════════════════════════════


class TestEVEngine:
    """Expected Value 엔진 테스트."""

    def test_ev_insufficient_trades(self):
        """이력 부족 시 EV None → 게이트 통과."""
        strategy = _make_strategy({"ev_min_trades": 5})
        # 3건만 기록
        for pnl in [0.02, -0.01, 0.03]:
            strategy.record_trade_result(pnl)
        ev = strategy._calculate_ev()
        assert ev is None
        assert strategy._check_ev_gate() is True

    def test_ev_blocks_negative(self):
        """EV ≤ 0 → 진입 차단."""
        strategy = _make_strategy({"ev_min_trades": 3})
        # 큰 손실 기록
        for pnl in [-0.05, -0.03, -0.04, 0.01, -0.06]:
            strategy.record_trade_result(pnl)
        ev = strategy._calculate_ev()
        assert ev is not None
        assert ev <= 0
        assert strategy._check_ev_gate() is False

    def test_ev_allows_positive(self):
        """EV > 0 → 진입 허용."""
        strategy = _make_strategy({"ev_min_trades": 3})
        for pnl in [0.05, 0.03, 0.04, -0.01, 0.06]:
            strategy.record_trade_result(pnl)
        ev = strategy._calculate_ev()
        assert ev > 0
        assert strategy._check_ev_gate() is True


class TestDynamicKelly:
    """Dynamic Kelly 테스트."""

    def test_kelly_insufficient_trades(self):
        """이력 부족 → 고정 kelly_fraction."""
        strategy = _make_strategy({"kelly_min_trades": 10, "kelly_fraction": 0.3})
        kelly = strategy._calculate_dynamic_kelly()
        assert kelly == 0.3

    def test_dynamic_kelly_bounds(self):
        """Kelly ∈ [0, kelly_max_fraction]."""
        strategy = _make_strategy({
            "kelly_min_trades": 3,
            "kelly_max_fraction": 0.5,
            "kelly_half_mult": 0.5,
        })
        # 승률 높은 이력
        for pnl in [0.05, 0.03, 0.04, -0.01, 0.06, 0.02, -0.005, 0.03, 0.04, 0.05]:
            strategy.record_trade_result(pnl)
        kelly = strategy._calculate_dynamic_kelly()
        assert 0 <= kelly <= 0.5

    def test_dynamic_kelly_bad_history(self):
        """나쁜 이력 → Kelly ≈ 0."""
        strategy = _make_strategy({
            "kelly_min_trades": 3,
            "kelly_max_fraction": 0.5,
            "kelly_half_mult": 0.5,
        })
        # 대부분 손실
        for pnl in [-0.05, -0.03, -0.04, 0.001, -0.06, -0.02]:
            strategy.record_trade_result(pnl)
        kelly = strategy._calculate_dynamic_kelly()
        assert kelly == 0.0  # 음수는 0으로 클램핑


# ══════════════════════════════════════════
# Phase 4A: 연속 손절 정지
# ══════════════════════════════════════════


class TestConsecutiveLossHalt:
    """연속 손절 정지 테스트."""

    def test_consecutive_loss_halt(self):
        """3회 연속 손실 → 진입 차단."""
        strategy = _make_strategy({"max_consecutive_losses": 3})
        strategy.record_trade_result(-0.02)
        strategy.record_trade_result(-0.01)
        assert strategy._check_consecutive_loss_halt() is True
        strategy.record_trade_result(-0.03)
        assert strategy._check_consecutive_loss_halt() is False

    def test_consecutive_loss_reset_on_win(self):
        """수익 발생 시 연속 손절 카운터 리셋."""
        strategy = _make_strategy({"max_consecutive_losses": 3})
        strategy.record_trade_result(-0.02)
        strategy.record_trade_result(-0.01)
        strategy.record_trade_result(0.05)  # 수익 → 리셋
        assert strategy._consecutive_losses == 0
        assert strategy._check_consecutive_loss_halt() is True

    def test_trade_history_lookback_limit(self):
        """이력 ev_lookback 초과 시 오래된 기록 제거."""
        strategy = _make_strategy({"ev_lookback": 5})
        for i in range(10):
            strategy.record_trade_result(0.01 * (i + 1))
        assert len(strategy._trade_history) == 5


# ══════════════════════════════════════════
# Phase 1B: KIS 시크릿 검증
# ══════════════════════════════════════════


class TestKISSecretValidation:
    """KIS 시크릿 검증 테스트."""

    def test_kis_secret_warning_live_mode(self, tmp_path, monkeypatch, caplog):
        """실전모드 빈 시크릿 → 경고 로그."""
        import logging
        from data.config_manager import ConfigManager

        monkeypatch.setenv("KIS_IS_PAPER", "false")
        monkeypatch.setenv("KIS_APP_KEY", "")
        monkeypatch.setenv("KIS_APP_SECRET", "")
        monkeypatch.setenv("KIS_ACCOUNT_NO", "")
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        cm = ConfigManager(config_path=str(tmp_path / "missing.yaml"))
        with caplog.at_level(logging.ERROR):
            config = cm.load()
        assert "LIVE MODE: kis_app_key is required but empty!" in caplog.text

    def test_kis_no_warning_paper_mode(self, tmp_path, monkeypatch, caplog):
        """모의모드 → 경고 없음."""
        import logging
        from data.config_manager import ConfigManager

        monkeypatch.setenv("KIS_IS_PAPER", "true")
        monkeypatch.setenv("KIS_APP_KEY", "")

        cm = ConfigManager(config_path=str(tmp_path / "missing.yaml"))
        with caplog.at_level(logging.ERROR):
            config = cm.load()
        assert "LIVE MODE" not in caplog.text
