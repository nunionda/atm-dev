# 이론-구현 Gap 분석

> 대상: `stock_theory/` (17개 이론 문서) vs `ats/` (실제 구현)
> 리뷰 일자: 2026-03-14

---

## 실제 구현된 파일 현황

`ats/` 디렉토리에 실제 존재하는 Python 파일:

```
ats/
├── common/enums.py, exceptions.py, types.py    # 공통 타입/열거형
├── core/__init__.py                             # (빈 파일)
├── data/config_manager.py                       # 설정 관리
├── infra/logger.py                              # 로거 (stub)
├── risk/__init__.py                             # (빈 파일)
├── strategy/base.py                             # 전략 추상 클래스
├── strategy/sp500_futures.py                    # S&P500 선물 전략 (1,129 LOC)
└── tests/test_sp500_futures.py                  # SP500 테스트
```

**CLAUDE.md에 언급되지만 미구현인 모듈 (25+개)**:

| 모듈 | CLAUDE.md 참조 | 상태 |
|------|---------------|------|
| `core/main_loop.py` | 4-Phase 매매 루프 | ❌ 미존재 |
| `core/state_manager.py` | FSM 상태관리 | ❌ 미존재 |
| `core/scheduler.py` | 매매 스케줄 | ❌ 미존재 |
| `strategy/momentum_swing.py` | 모멘텀 스윙 전략 | ❌ 미존재 |
| `strategy/smc_strategy.py` | SMC 4-Layer 전략 | ❌ 미존재 |
| `strategy/breakout_retest.py` | 돌파-리테스트 전략 | ❌ 미존재 |
| `risk/risk_manager.py` | 리스크 게이트 | ❌ 미존재 |
| `order/order_executor.py` | 주문 실행 | ❌ 미존재 |
| `position/position_manager.py` | 포지션 관리 | ❌ 미존재 |
| `infra/broker/kis_broker.py` | KIS API 브로커 | ❌ 미존재 |
| `infra/db/models.py` | ORM 모델 | ❌ 미존재 |
| `infra/db/repository.py` | 데이터 접근 | ❌ 미존재 |
| `infra/notifier/telegram_notifier.py` | 텔레그램 알림 | ❌ 미존재 |
| `analytics/indicators.py` | 기술 지표 계산 | ❌ 미존재 |
| `simulation/engine.py` | 시뮬레이션 엔진 | ❌ 미존재 |
| `backtest/historical_engine.py` | 히스토리컬 백테스트 | ❌ 미존재 |
| `backtest/metrics.py` | 성과 지표 | ❌ 미존재 |
| `data/market_data.py` | 시장 데이터 | ❌ 미존재 |

---

## 전략별 정합률 매트릭스

### Strategy 1: S&P500 선물 (4-Layer Scoring)

| 기능 | 이론 문서 | Config | 코드 | 상태 |
|------|----------|--------|------|------|
| Z-Score 계산 | futuresStrategy.md | ✅ | ✅ | ✅ |
| 4-Layer 스코어링 (100점) | futuresStrategy.md | ✅ | ✅ | ✅ |
| ATR 돌파 필터 | future_trading_stratedy.md | ✅ | ✅ | ✅ |
| Dynamic ATR 배수 (ADX 기반) | future_trading_stratedy.md | ✅ | ✅ | ✅ |
| 7단계 청산 cascade | ExitStrategyIndex.md | ✅ | ✅ | ✅ |
| 샹들리에 청산 | ExitStrategyIndex.md | ✅ | ✅ | ✅ |
| Progressive Trailing | mddDefenceStrategy.md | ⚠️ 2-tier | ⚠️ | ⚠️ |
| Expected Value 엔진 | futuresStrategy.md | ❌ | ❌ | ❌ |
| 동적 Kelly Criterion | Kelly Criterion.md | ❌ | ⚠️ 고정 0.3 | ⚠️ |
| 위크 트랩 감지 | 자체 구현 | ❌ | ✅ | ✅ |

**정합률: ~75%** (핵심 기능 구현, EV/Kelly 미구현)

---

### Strategy 2: 모멘텀 스윙 (6-Phase Pipeline)

| Phase | 이론 | Config | 코드 | 상태 |
|-------|------|--------|------|------|
| Phase 0: Market Regime | alphaStrategy.md | ❌ | ❌ | ❌ |
| Phase 1: Trend Confirm (MA/ADX) | alphaStrategy.md | ✅ strategy 섹션 | ❌ | ❌ |
| Phase 2: Trend Stage (BB/RSI) | alphaStrategy.md | ⚠️ | ❌ | ❌ |
| Phase 3: Entry Signal (PS1+PS2, CF1+CF2) | alphaStrategy.md | ✅ | ❌ | ❌ |
| Phase 4: Risk Gate (RG1-RG4) | mddDefenceStrategy.md | ✅ risk 섹션 | ❌ | ❌ |
| Phase 5: Exit (ES1-ES7) | ExitStrategyIndex.md | ✅ exit 섹션 | ❌ | ❌ |
| Signal Strength Score (0-100) | alphaStrategy.md | ❌ | ❌ | ❌ |
| Position Sizing (quality mult) | alphaStrategy.md | ❌ | ❌ | ❌ |

**정합률: ~5%** (Config 존재하지만 코드 파일 자체가 미존재)

---

### Strategy 3: SMC 4-Layer Scoring

| 기능 | 이론 | Config | 코드 | 상태 |
|------|------|--------|------|------|
| BOS/CHoCH 감지 | smcTheory.md | ✅ | ❌ | ❌ |
| Swing Point 프랙탈 | smcTheory.md | ✅ | ❌ | ❌ |
| 4-Layer (SMC+BB+OBV+Momentum) | smcTheory.md | ✅ | ❌ | ❌ |
| Order Block/FVG 추적 | smcTheory.md | ✅ | ❌ | ❌ |
| ATR SL/TP | smcTheory.md | ✅ | ❌ | ❌ |
| CHoCH 반전 청산 | smcTheory.md | ✅ | ❌ | ❌ |

**정합률: ~10%** (Config 완전, 코드 0%)

---

### Strategy 4: Breakout-Retest

| 기능 | 이론 | Config | 코드 | 상태 |
|------|------|--------|------|------|
| Phase A: 돌파 감지 4-Layer | CLAUDE.md | ✅ | ❌ | ❌ |
| 6조건 (4/6 필수) | CLAUDE.md | ✅ | ❌ | ❌ |
| 3 페이크아웃 필터 | CLAUDE.md | ✅ | ❌ | ❌ |
| Phase B: 리테스트 진입 | CLAUDE.md | ✅ | ❌ | ❌ |
| Retest Zone 스코어링 | CLAUDE.md | ✅ | ❌ | ❌ |
| BRT Exit Rules | CLAUDE.md | ✅ | ❌ | ❌ |

**정합률: ~10%** (Config 완전, 코드 0%)

---

### MDD Defence — 7-Layer Architecture

| Layer | 이론 | 구현 | 상태 |
|-------|------|------|------|
| L1: Market Regime | mddDefenceStrategy.md | ❌ | ❌ |
| L2: Trend Filter (Phase 1-2) | mddDefenceStrategy.md | ❌ | ❌ |
| L3: Signal Quality (Phase 3) | mddDefenceStrategy.md | ❌ | ❌ |
| L4: Risk Gates (RG1-RG4) | mddDefenceStrategy.md | ❌ risk_manager.py 미존재 | ❌ |
| L5: ATR Position Sizing | mddDefenceStrategy.md | ⚠️ sp500만 | ⚠️ |
| L6: 5-Stage Exit Priority | mddDefenceStrategy.md | ⚠️ sp500만 | ⚠️ |
| L7: Progressive Trailing | mddDefenceStrategy.md | ⚠️ 2-tier 단순화 | ⚠️ |

**정합률: ~15%** (SP500 전략에서 L5-L7 부분 구현)

---

## 핵심 파라미터 불일치 (3건)

### D1. 손절 비율

| 항목 | CLAUDE.md | config.yaml | sp500_futures.py |
|------|----------|-------------|------------------|
| BR-S01 하드 손절 | **-10%** (개별 종목) | `stop_loss_pct: -0.05` (-5%) | `sl_hard_pct: 0.03` (-3%) |

3가지 문서/코드에서 모두 다른 값 사용.

### D2. 트레이드당 리스크

| 항목 | CLAUDE.md (BR-P04) | config.yaml | sp500_futures.py |
|------|-------------------|-------------|------------------|
| Risk per trade | **1.5%** of equity | `risk_per_trade_pct: 0.015` (1.5%) | 하드코딩 1.5% |

여기서는 일치하지만, CLAUDE.md MDD Defence 섹션에서는 "1% risk/trade"로 언급.

### D3. 최대 보유일

| 항목 | CLAUDE.md | config.yaml exit | sp500_futures config |
|------|----------|------------------|---------------------|
| 모멘텀 스윙 | BULL 40 / NEUTRAL 25 / BEAR 15 | `max_holding_days: 40` (BULL 고정) | N/A |
| SP500 선물 | 명시 없음 | N/A | `max_holding_days: 20` |

레짐별 동적 보유일이 config에서 단일 값으로 단순화됨.

---

## 이론 문서 구현 현황 종합

| 이론 문서 | 구현 상태 | 비고 |
|----------|----------|------|
| futuresStrategy.md | ✅ **거의 완전** | EV엔진 제외 |
| future_trading_stratedy.md | ✅ **거의 완전** | ATR 기반 구현 |
| ExitStrategyIndex.md | ⚠️ SP500만 | 모멘텀/SMC/BRT 미적용 |
| Kelly Criterion.md | ⚠️ 고정값만 | 동적 Kelly 미구현 |
| alphaStrategy.md | ❌ **미구현** | 전략 파일 미존재 |
| smcTheory.md | ❌ **미구현** | Config만 존재 |
| mddDefenceStrategy.md | ❌ **미구현** | 7-Layer 중 0개 독립 구현 |
| TradingLogicFlow.md | ❌ **미구현** | 이론→구현 매핑 미적용 |
| trendTheory.md | ❌ **미구현** | 매크로 4필터 미구현 |
| scalpingPlaybook.md | ❌ **미구현** | 프론트엔드 UI만 |
| BlackScholesEquation.md | ⚠️ FE만 | 프론트엔드 계산기만 |

---

## 결론

**전체 이론-구현 정합률: ~25%**

- SP500 선물 전략만 실질적으로 구현 완료 (75%)
- 나머지 4개 전략은 Config만 존재하고 코드 파일 자체가 미존재
- CLAUDE.md에 기술된 25+ 모듈 중 실제 존재하는 것은 8개 (common, config, logger, base, sp500_futures, tests)
- `main.py`가 참조하는 13개 모듈 중 대부분 미구현 → 시스템 시작 불가
- MDD 7-Layer 방어 체계 완전 미구현 → 프로덕션 리스크 관리 부재
