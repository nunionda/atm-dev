# Strategy Matrix Analysis Report
Generated: 2026-03-12 06:34
Period: 20240101 ~ 20260228

## 1. Performance Matrix

### Sharpe Ratio
| Market | momentum | mean_reversion | smc | breakout_retest | multi |
|--------|--------|--------|--------|--------|--------|
| SP500 | 0.62 | 2.32 | 0.97 | 2.38 | 2.53 |
| NDX | 1.17 | 1.33 | 1.19 | 3.18 | 1.43 |
| KOSPI | 1.88 | 2.13 | 1.73 | 1.54 | 2.13 |

### Total Return
| Market | momentum | mean_reversion | smc | breakout_retest | multi |
|--------|--------|--------|--------|--------|--------|
| SP500 | +16.8% | +12.3% | +31.0% | +1.9% | +13.0% |
| NDX | +38.3% | +10.4% | +38.5% | +1.5% | +11.1% |
| KOSPI | +52.3% | +5.9% | +37.7% | +1.7% | +6.1% |

### Profit Factor
| Market | momentum | mean_reversion | smc | breakout_retest | multi |
|--------|--------|--------|--------|--------|--------|
| SP500 | 1.32 | 2.83 | 1.44 | 5.76 | 3.15 |
| NDX | 1.82 | 1.74 | 1.51 | 4.78 | 1.83 |
| KOSPI | 1.84 | 1.87 | 1.85 | 2.25 | 1.86 |

### Max Drawdown
| Market | momentum | mean_reversion | smc | breakout_retest | multi |
|--------|--------|--------|--------|--------|--------|
| SP500 | -13.44% | -3.21% | -8.26% | -0.87% | -2.86% |
| NDX | -10.16% | -5.75% | -10.32% | -0.96% | -5.45% |
| KOSPI | -6.89% | -3.21% | -7.99% | -1.55% | -3.41% |

## 2. Best Strategy per Market

- **SP500**: multi (Sharpe 2.53, Return +13.0%, PF 3.15)
- **NDX**: breakout_retest (Sharpe 3.18, Return +1.5%, PF 4.78)
- **KOSPI**: mean_reversion (Sharpe 2.13, Return +5.9%, PF 1.87)

## 3. Improvement Recommendations

1. [sp500/momentum] Phase1 거부율 4% < 50% → 필터 부족, 강화 검토
2. [sp500/momentum] 단기(≤3일) 손실률 93% > 50% → 휩소(whipsaw) 문제
3. [sp500/mean_reversion] 단기(≤3일) 손실률 78% > 50% → 휩소(whipsaw) 문제
4. [sp500/smc] ES1 손절 비율 31% > 30% → 진입 타이밍/필터 개선 필요
5. [sp500/smc] Phase1 거부율 0% < 50% → 필터 부족, 강화 검토
6. [sp500/smc] 단기(≤3일) 손실률 80% > 50% → 휩소(whipsaw) 문제
7. [sp500/breakout_retest] Phase1 거부율 0% < 50% → 필터 부족, 강화 검토
8. [sp500/multi] 단기(≤3일) 손실률 75% > 50% → 휩소(whipsaw) 문제
9. [ndx/momentum] Phase1 거부율 8% < 50% → 필터 부족, 강화 검토
10. [ndx/momentum] 단기(≤3일) 손실률 89% > 50% → 휩소(whipsaw) 문제
11. [ndx/mean_reversion] 단기(≤3일) 손실률 59% > 50% → 휩소(whipsaw) 문제
12. [ndx/smc] ES1 손절 비율 32% > 30% → 진입 타이밍/필터 개선 필요
13. [ndx/smc] Phase1 거부율 0% < 50% → 필터 부족, 강화 검토
14. [ndx/smc] 단기(≤3일) 손실률 86% > 50% → 휩소(whipsaw) 문제
15. [ndx/breakout_retest] Phase1 거부율 0% < 50% → 필터 부족, 강화 검토
16. [ndx/multi] 단기(≤3일) 손실률 56% > 50% → 휩소(whipsaw) 문제
17. [kospi/momentum] ES1 손절 비율 34% > 30% → 진입 타이밍/필터 개선 필요
18. [kospi/momentum] Phase1 거부율 4% < 50% → 필터 부족, 강화 검토
19. [kospi/momentum] 단기(≤3일) 손실률 91% > 50% → 휩소(whipsaw) 문제
20. [kospi/mean_reversion] ES1 손절 비율 47% > 30% → 진입 타이밍/필터 개선 필요
21. [kospi/mean_reversion] 단기(≤3일) 손실률 100% > 50% → 휩소(whipsaw) 문제
22. [kospi/smc] ES1 손절 비율 45% > 30% → 진입 타이밍/필터 개선 필요
23. [kospi/smc] Phase1 거부율 0% < 50% → 필터 부족, 강화 검토
24. [kospi/smc] 단기(≤3일) 손실률 86% > 50% → 휩소(whipsaw) 문제
25. [kospi/breakout_retest] Phase1 거부율 0% < 50% → 필터 부족, 강화 검토
26. [kospi/multi] ES1 손절 비율 47% > 30% → 진입 타이밍/필터 개선 필요
27. [kospi/multi] 단기(≤3일) 손실률 100% > 50% → 휩소(whipsaw) 문제
28. [momentum] Sharpe 시장 간 편차 1.25 > 1.0 (sp500:0.62, ndx:1.17, kospi:1.88) → 시장 특화 튜닝 필요
29. [breakout_retest] Sharpe 시장 간 편차 1.64 > 1.0 (sp500:2.38, ndx:3.18, kospi:1.54) → 시장 특화 튜닝 필요
30. [multi] Sharpe 시장 간 편차 1.10 > 1.0 (sp500:2.53, ndx:1.43, kospi:2.13) → 시장 특화 튜닝 필요
31. [BULL] 레짐 승률 43% < 50% → 레짐 판단 부정확 또는 진입 시그널 약함

## 4. Trade Summary

| Market/Strategy | Trades | Win Rate | Avg PnL% | Best | Worst |
|-----------------|--------|----------|----------|------|-------|
| sp500/momentum | 189 | 40% | +0.87% | +33.6% | -12.9% |
| sp500/mean_reversion | 34 | 56% | +2.35% | +16.6% | -5.2% |
| sp500/smc | 232 | 43% | +1.12% | +23.1% | -12.4% |
| sp500/breakout_retest | 3 | 67% | +4.61% | +14.0% | -2.9% |
| sp500/multi | 33 | 58% | +2.58% | +16.6% | -5.2% |
| ndx/momentum | 217 | 45% | +1.61% | +26.8% | -19.2% |
| ndx/mean_reversion | 52 | 56% | +1.49% | +16.6% | -8.9% |
| ndx/smc | 296 | 42% | +0.99% | +25.3% | -25.4% |
| ndx/breakout_retest | 2 | 50% | +5.55% | +14.0% | -2.9% |
| ndx/multi | 51 | 57% | +1.62% | +16.6% | -8.9% |
| kospi/momentum | 150 | 36% | +1.80% | +46.1% | -16.9% |
| kospi/mean_reversion | 21 | 52% | +2.07% | +18.1% | -8.1% |
| kospi/smc | 218 | 39% | +2.75% | +52.0% | -12.6% |
| kospi/breakout_retest | 5 | 40% | +2.38% | +19.6% | -4.3% |
| kospi/multi | 21 | 52% | +2.07% | +18.1% | -8.1% |
