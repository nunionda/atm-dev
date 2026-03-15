# 5-Year KOSPI 200 Multi-Strategy Backtest Report

**Date:** 2026-03-16
**Period:** 2021-03-16 ~ 2026-03-16 (1,255 trading days)
**Strategy:** multi (all strategies)
**Universe:** kospi_full (KOSPI 200 stocks, 14-day rebalancing)
**Initial Capital:** ₩100,000,000
**Raw Data:** `data_store/backtest_5yr_kospi_multi_20210316_20260316.json`

---

## 1. Summary Metrics

| Metric | Value |
|--------|-------|
| Total Return | **0.0%** |
| Trades | **0** |
| Final Value | ₩100,000,000 |
| Risk Blocks | 3,083 |
| Total Rebalances | 88 |

---

## 2. Regime Distribution

| Regime | Time % |
|--------|--------|
| BULL | 26.8% |
| NEUTRAL | 69.1% |
| BEAR | 4.1% |

---

## 3. Stock Regime Distribution

| Stock Regime | Count |
|-------------|-------|
| NEUTRAL | 69 (84%) |
| BEAR | 13 (16%) |

---

## 4. Analysis: Why 0 Trades

KOSPI 백테스트에서 거래가 0건 발생한 원인:

1. **phase4_risk_blocks = 3,083**: 리스크 게이트가 모든 진입을 차단
2. **total_scans = 0**: 전략 스캔 자체가 0회 — 종목 데이터 부족 또는 필터 미통과
3. **Data quality**: yfinance의 KRX(한국) 주식 데이터는 글로벌 대비 품질/가용성 낮음
   - 일부 종목 히스토리 부족 (200봉 미만)
   - KRX 종목 코드(.KS, .KQ) 인식률 제한
4. **Stock regime clustering**: 82 종목 중 84%가 NEUTRAL, 16%가 BEAR
   - 새 affinity 테이블에서 NEUTRAL → momentum 0.0, breakout_retest 0.0
   - BEAR → momentum 0.0, breakout_retest 0.0
   - Mean Reversion과 SMC만 가능하나 데이터 부족으로 스캔 불가

### 해결 방안

1. KOSPI는 KIS(한국투자증권) API 또는 Naver Finance 크롤링으로 데이터 보완 필요
2. KOSPI 전용 워밍업 기간 단축 (200봉 → 120봉 옵션)
3. 종목별 레짐 affinity에서 NEUTRAL의 momentum 허용 (현재 0.0 → 0.2) 검토

---

## 5. Comparison Baseline

```
KOSPI 5-Year Baseline (2021-03-16 ~ 2026-03-16):
  Return: 0.0%   |  Sharpe: 0.0   |  MDD: 0.0%
  Trades: 0       |  WR: N/A      |  PF: N/A
  Final: ₩100,000,000
  Note: No trades due to data/risk gate limitations
```
