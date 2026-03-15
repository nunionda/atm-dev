# ATS Frontend Menu Restructure — Workflow-Centered Navigation

**Date**: 2026-03-15
**Status**: Design Approved
**Scope**: Navbar restructure, route migration, Signal Lab Overview page

---

## Problem

현재 Navbar에 8개 메인 메뉴가 평면적으로 나열되어 있어 매매 플로우를 파악하기 어렵다.
주식/선물/옵션 분석이 각각 별도 메뉴로 흩어져 있어 한눈에 보기 힘들다.

## Design Decision

**워크플로우 중심 3-그룹 구조** — 트레이더의 자연스러운 사고 흐름에 맞춤:

1. **Signal Lab** — "뭘 살까?" (분석 → 신호 → 진입 판단)
2. **Trading** — "지금 괜찮아?" (포지션 → 리스크 → 주문)
3. **Review** — "얼마나 벌었어?" (성과 → 백테스트 → 리밸런싱)

---

## Navigation Structure

### Main Navbar

```
┌─────────────────────────────────────────────────────────────────┐
│  📈 ATS   [Home]  [Signal Lab ▾]  [Trading ▾]  [Review ▾]  📖  │
└─────────────────────────────────────────────────────────────────┘
```

- 8개 → 3개 메인 메뉴로 축소
- Theory는 우측 아이콘(📖)으로 이동 (보조 메뉴)
- 각 메뉴 hover 시 드롭다운 표시 (데스크톱), 모바일은 hamburger + accordion
- Active state: 현재 URL이 그룹 prefix로 시작하면 해당 그룹 하이라이트 (e.g., `/signals/stocks` → Signal Lab active)

### Dropdown Menus

```
[Signal Lab ▾]              [Trading ▾]           [Review ▾]
┌──────────────────┐    ┌────────────────┐    ┌─────────────────┐
│ 📊 Overview      │    │ 📋 Operations  │    │ 📈 Performance  │
│ ─────────────── │    │ 🛡️ Risk        │    │ 🧪 Backtest     │
│ 🏢 Stocks       │    └────────────────┘    │ ⚖️ Rebalance    │
│ 📉 Futures      │                          └─────────────────┘
│ 🧮 Options      │
└──────────────────┘
```

---

## Route Mapping

| Old Route | New Route | Group | Component |
|-----------|-----------|-------|-----------|
| `/` | `/` | Home | Home |
| — | `/signals` | Signal Lab | **SignalOverview (신규)** |
| `/dashboard` | `/signals/stocks` | Signal Lab | Dashboard |
| `/scalp-analyzer` | `/signals/futures` | Signal Lab | ScalpAnalyzer |
| `/scalp-analyzer/fabio` | `/signals/futures/fabio` | Signal Lab | FabioStrategy |
| `/option-calculator` | `/signals/options` | Signal Lab | OptionCalculator |
| `/operations` | `/trading/operations` | Trading | Operations |
| `/risk` | `/trading/risk` | Trading | Risk |
| `/performance` | `/review/performance` | Review | Performance |
| — | `/review/backtest` | Review | **BacktestPage (Rebalance에서 분리)** |
| `/rebalance` | `/review/rebalance` | Review | Rebalance (백테스트 제거) |
| `/theory/*` | `/theory/*` | 우측 아이콘 | Theory (wildcard 유지) |

### Default Routes (그룹 진입 시)

- `/signals` → Signal Lab Overview (자산군 탭 없이 3-카드 요약)
- `/trading` → `/trading/operations`로 리다이렉트
- `/review` → `/review/performance`로 리다이렉트

### Legacy Route Redirects

기존 북마크/딥링크 호환을 위한 리다이렉트 (React Router `<Navigate>`):

| Old Route | Redirect To |
|-----------|-------------|
| `/dashboard` | `/signals/stocks` |
| `/scalp-analyzer` | `/signals/futures` |
| `/scalp-analyzer/fabio` | `/signals/futures/fabio` |
| `/option-calculator` | `/signals/options` |
| `/operations` | `/trading/operations` |
| `/risk` | `/trading/risk` |
| `/performance` | `/review/performance` |
| `/rebalance` | `/review/rebalance` |

---

## Page Designs

### Signal Lab Overview (`/signals`) — 신규

3개 자산군 시그널을 한 화면에 요약하는 랜딩 페이지:

```
┌─────────────────────────────────────────────────────┐
│  Signal Lab                    Market Regime: BULL 🟢│
├─────────────┬─────────────┬─────────────────────────┤
│  🏢 Stocks  │ 📉 Futures  │  🧮 Options             │
│  ────────── │  ────────── │  ──────────              │
│  활성 시그널 3 │  Z-Score    │  IV Rank               │
│  상위 종목    │  ATR 상태   │  Put/Call Ratio         │
│  시그널 점수  │  스캘프 기회 │  주요 만기              │
│  [상세 →]    │  [상세 →]    │  [상세 →]              │
└─────────────┴─────────────┴─────────────────────────┘
```

- 각 카드 클릭 시 해당 자산 상세 페이지로 이동
- Market Regime은 현재 MarketRegimePanel 데이터 재사용

### Sub-Navigation Pattern (공통)

Signal Lab 내부 페이지:
```
┌──────────────────────────────────────────────────────┐
│  Signal Lab > [Stocks] [Futures] [Options]            │ ← 자산군 탭 (항상)
│  [Chart & Analysis] [Signal Scanner] [Regime]         │ ← 자산별 서브탭
├──────────────────────────────────────────────────────┤
│  콘텐츠                                               │
└──────────────────────────────────────────────────────┘
```

Trading / Review 내부 페이지:
```
┌──────────────────────────────────────────────────────┐
│  Trading > [Operations] [Risk]                        │ ← 서브탭
│  Market: [US] [KR] [KOSPI200]                         │ ← 마켓 탭 (공유)
├──────────────────────────────────────────────────────┤
│  콘텐츠                                               │
└──────────────────────────────────────────────────────┘
```

- 서브탭 전환 시 선택된 마켓 유지 (AppStateContext)
- Risk 이상 감지 시 Risk 탭에 뱃지(🔴) 표시

---

## Stocks Sub-Tabs

| Tab | Content | Source |
|-----|---------|--------|
| Chart & Analysis (기본) | TechnicalChart + SignalAnalysis + ChartToolbar + TickerSearch | 현재 Dashboard |
| Signal Scanner | ScanSummary + RecommendationTable (유니버스 스캔) | 현재 Rebalance에서 이동 |
| Regime | MarketRegimePanel 확장 (브레드스, 히스토리) | 현재 Dashboard |

## Futures Sub-Tabs

| Tab | Content | Source |
|-----|---------|--------|
| Scalp Analyzer (기본) | Z-Score + ATR + Position Calculator | 현재 ScalpAnalyzer |
| Fabio Strategy | AMT 3-Stage + Triple-A Model | 현재 FabioStrategy |

## Options Sub-Tabs

| Tab | Content | Source |
|-----|---------|--------|
| Calculator (기본) | Black-Scholes Calculator + Presets | 현재 OptionCalculator |
| Greeks Dashboard | (향후 확장) | — |

---

## Trading Section

### Operations (`/trading/operations`)

현재 Operations 페이지 그대로 유지:
- SystemStatusBar, SimControlBar
- PositionTable, StrategyWeightPanel
- SignalList, OrderLog
- MiniEquityCurve, OpsRiskGauges
- MarketIntelligenceBar

### Risk (`/trading/risk`)

현재 Risk 페이지 그대로 유지:
- Emergency Controls (Pause / Force Liquidate)
- RiskGauge × 3 (Daily PnL, MDD, Cash)
- RiskGateStatus (RG1-RG4)
- DrawdownChart, PositionRiskTable, RiskEventLog

---

## Review Section

### Performance (`/review/performance`)

현재 Performance 페이지 그대로 유지:
- PerformanceMetrics, BenchmarkComparison
- EquityCurve, TradeLogTable

### Backtest (`/review/backtest`) — Rebalance에서 분리

현재 BacktestSection 컴포넌트를 독립 페이지로 승격:
- 전략 선택 (Momentum / SMC / BRT / Multi)
- 파라미터 설정, 기간/유니버스 선택
- 결과: Equity Curve + Metrics + Trade Log

### Rebalance (`/review/rebalance`)

현재 Rebalance에서 BacktestSection 제거:
- RebalanceHeader (스캔 트리거)
- ScanSummary (BUY / HOLD / SELL 카운트)
- RecommendationTable × 3

Signal Scanner(Signal Lab > Stocks)와 데이터 공유하되 관점 차이:
- Signal Scanner: "진입할 종목은?" (분석 관점)
- Rebalance: "포트폴리오 조정은?" (운용 관점)
- **구현**: 동일 API 엔드포인트 (`/rebalance/scan`, `/rebalance/recommendations`) 호출. 각 컴포넌트가 독립적으로 fetch (공유 캐시 불필요 — 페이지 전환 시 최신 데이터 보장)

---

## Component Changes Summary

| Change | Type | Detail |
|--------|------|--------|
| Navbar.tsx + CSS | **수정** | 드롭다운 3-그룹 구조로 재작성 (hover 드롭다운, 모바일 accordion) |
| App.tsx | **수정** | 라우트 재구성 (nested routes) + legacy redirect |
| SignalOverview.tsx | **신규** | 3자산 시그널 요약 랜딩 페이지 |
| SubNavigation.tsx | **신규** | 공통 서브 네비게이션 컴포넌트 |
| BacktestPage.tsx | **신규** | BacktestSection을 감싸는 페이지 |
| Dashboard.tsx | **수정** | Signal Scanner 탭 추가, 서브탭 구조 |
| ScalpAnalyzer.tsx | **수정** | 서브탭 구조 적용, 내부 Link 경로 업데이트 |
| FabioStrategy.tsx | **수정** | 내부 Link 경로 업데이트 (`/scalp-analyzer` → `/signals/futures`) |
| OptionCalculator.tsx | **수정** | 서브탭 구조 적용 |
| Rebalance.tsx | **수정** | BacktestSection 제거 |
| Operations.tsx | **수정 최소** | 라우트 경로만 변경 |
| Risk.tsx | **수정 최소** | 라우트 경로만 변경 |
| Performance.tsx | **수정 최소** | 라우트 경로만 변경 |

---

## Non-Goals

- 페이지 내부 레이아웃 대폭 변경 (기존 컴포넌트 재사용)
- 새로운 API 엔드포인트 추가
- 백엔드 변경
- 실시간 데이터 플로우 변경

## Risks

- **라우트 변경 시 북마크/딥링크 깨짐**: 기존 라우트에서 새 라우트로 리다이렉트 추가로 해결
- **Signal Lab Overview 데이터**: 기존 API 조합으로 구성 가능 (새 API 불필요)
