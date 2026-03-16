# CSS Design System Unification Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 43개 CSS 파일에 흩어진 스타일을 디자인 토큰 + 공통 컴포넌트 클래스로 통일하여 일관된 UI 제공

**Architecture:** index.css에 디자인 토큰(CSS 변수) 추가 → 공통 컴포넌트 클래스 정의 → 각 페이지 CSS에서 하드코딩 제거 + 공통 클래스 참조

**Tech Stack:** CSS Custom Properties (변수), 기존 index.css 확장

---

## Design Token Specification

### 1. Typography Scale

```
--font-xs:    0.75rem   (12px) — 보조 라벨, 타임스탬프
--font-sm:    0.8125rem (13px) — 테이블 셀, 작은 라벨
--font-base:  0.875rem  (14px) — 기본 본문
--font-md:    1rem      (16px) — 카드 제목, 강조 텍스트
--font-lg:    1.25rem   (20px) — 섹션 제목
--font-xl:    1.5rem    (24px) — 페이지 제목
--font-2xl:   2rem      (32px) — 히어로 (Home만)
```

### 2. Spacing Scale (4px base)

```
--space-1:  0.25rem  (4px)
--space-2:  0.5rem   (8px)
--space-3:  0.75rem  (12px)
--space-4:  1rem     (16px)
--space-5:  1.25rem  (20px)
--space-6:  1.5rem   (24px)
--space-8:  2rem     (32px)
```

### 3. Border Radius Scale

```
--radius-sm:  6px   — 인풋, 뱃지, 필
--radius-md:  10px  — 카드, 패널
--radius-lg:  14px  — 모달, 대형 패널
--radius-full: 100px — 버튼, 태그
```

### 4. Shadows

```
--shadow-card:   0 2px 8px rgba(0,0,0,0.3)          — 기본 카드
--shadow-panel:  0 4px 12px rgba(0,0,0,0.4)          — 떠있는 패널
--shadow-float:  0 8px 24px rgba(0,0,0,0.5)          — 드롭다운, 모달
```

### 5. Component Tokens

```
--card-bg:       rgba(255,255,255,0.03)
--card-border:   rgba(255,255,255,0.06)
--card-padding:  var(--space-4)                       (16px)
--card-radius:   var(--radius-md)                     (10px)

--input-bg:      rgba(255,255,255,0.05)
--input-border:  rgba(255,255,255,0.1)
--input-radius:  var(--radius-sm)                     (6px)
--input-padding:  0.5rem 0.75rem

--table-header-bg:    rgba(255,255,255,0.03)
--table-cell-padding: 0.625rem 0.75rem                (10px 12px)
--table-border:       rgba(255,255,255,0.06)
```

---

## Common Component Classes

### `.card` (범용 카드)
```css
.card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: var(--card-radius);
  padding: var(--card-padding);
}
```

### `.card-header` (카드 제목 영역)
```css
.card-header {
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
}
```

### `.metric-value` (숫자 강조)
```css
.metric-value {
  font-size: var(--font-lg);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.metric-label {
  font-size: var(--font-xs);
  font-weight: 500;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
```

### `.data-table` (테이블 공통)
```css
.data-table { width: 100%; border-collapse: collapse; }
.data-table th {
  padding: var(--table-cell-padding);
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--text-secondary);
  text-align: left;
  border-bottom: 1px solid var(--table-border);
  background: var(--table-header-bg);
}
.data-table td {
  padding: var(--table-cell-padding);
  font-size: var(--font-sm);
  color: var(--text-primary);
  border-bottom: 1px solid var(--table-border);
}
```

### `.input-field` (인풋 공통)
```css
.input-field {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  padding: var(--input-padding);
  color: var(--text-primary);
  font-size: var(--font-base);
  font-family: inherit;
}
.input-field:focus {
  border-color: var(--accent-primary);
  outline: none;
}
```

### `.page-container` (페이지 레이아웃)
```css
.page-container {
  max-width: 1400px;
  margin: var(--space-6) auto;
  padding: 0 var(--space-6);
}
.page-title {
  font-size: var(--font-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-5);
}
.section-title {
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
}
```

### `.badge` / `.pill` (태그/뱃지)
```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.6rem;
  font-size: var(--font-xs);
  font-weight: 600;
  border-radius: var(--radius-full);
  white-space: nowrap;
}
.badge--green  { background: rgba(34,197,94,0.15); color: #4ade80; }
.badge--red    { background: rgba(239,68,68,0.15); color: #f87171; }
.badge--yellow { background: rgba(234,179,8,0.15); color: #facc15; }
.badge--blue   { background: rgba(59,130,246,0.15); color: #60a5fa; }
.badge--muted  { background: rgba(255,255,255,0.05); color: var(--text-secondary); }
```

### PnL 컬러 (손익 표시)
```css
.pnl-positive { color: #4ade80; }
.pnl-negative { color: #f87171; }
.pnl-neutral  { color: var(--text-secondary); }
```

---

## File Change Map

| File | Action | Detail |
|------|--------|--------|
| `index.css` | **확장** | 디자인 토큰 + 공통 컴포넌트 클래스 추가 |
| `ScalpAnalyzer.css` | **수정** | 하드코딩 색상 → CSS변수, radius/padding 통일 |
| `FabioStrategy.css` | **수정** | 하드코딩 색상 → CSS변수, radius/padding 통일 |
| `Dashboard.css` | **수정** | radius/padding 토큰 적용 |
| `Operations.css` | **수정** | page-title 크기 통일 |
| `Risk.css` | **수정** | 토큰 적용 |
| `Performance.css` | **수정** | 토큰 적용 |
| `Rebalance.css` | **수정** | radius/padding/border 토큰 적용 |
| `Home.css` | **수정** | card 토큰 적용 |
| `OptionCalculator.css` | **수정** | input/card 토큰 적용 |
| `SignalOverview.css` | **수정** | 토큰 적용 |
| `OpsPerformanceCards.css` | **수정** | card padding 통일 |
| `PositionTable.css` | **수정** | table 토큰 적용 |
| `PerformanceMetrics.css` | **수정** | card/metric 토큰 적용 |
| `RiskGauge.css` | **수정** | card 토큰 적용 |

---

## Chunk 1: 디자인 토큰 + 공통 클래스 추가

### Task 1: index.css에 디자인 토큰 추가

**Files:**
- Modify: `web/src/index.css` (:root 블록에 토큰 추가)

- [ ] **Step 1: :root에 Typography, Spacing, Radius, Shadow, Component 토큰 추가**

위 Design Token Specification 전체를 `:root` 블록 끝에 추가.

- [ ] **Step 2: 공통 컴포넌트 클래스 추가**

위 Common Component Classes 전체를 index.css 하단에 추가.
기존 `.glass-panel`, `.btn-primary`, `.btn-secondary`, `.container`는 유지.

- [ ] **Step 3: 기존 glass-panel border-radius를 토큰으로 교체**

`.glass-panel`의 `border-radius: 16px` → `border-radius: var(--radius-lg)`

- [ ] **Step 4: Commit**

```bash
git add web/src/index.css
git commit -m "feat: 디자인 토큰 + 공통 컴포넌트 클래스 추가 (index.css)"
```

---

## Chunk 2: ScalpAnalyzer + FabioStrategy 하드코딩 제거 (가장 큰 불일치)

### Task 2: ScalpAnalyzer.css 하드코딩 → CSS 변수

**Files:**
- Modify: `web/src/pages/ScalpAnalyzer.css`

- [ ] **Step 1: 페이지 배경 하드코딩 제거**

```css
/* before */ background: #060910;
/* after  */ background: var(--bg-primary);
```

- [ ] **Step 2: .scalp-box 토큰 적용**

```css
/* before */ border-radius: 10px; padding: 18px; border: 1px solid #1c2336;
/* after  */ border-radius: var(--card-radius); padding: var(--card-padding); border: 1px solid var(--card-border);
```

- [ ] **Step 3: 하드코딩 색상 전부 CSS 변수로 교체**

주요 매핑:
- `#6b7594` → `var(--text-secondary)`
- `#a0aec0`, `#8899bb` → `var(--text-secondary)`
- `#e2e8f0`, `#f1f5f9` → `var(--text-primary)`
- `#1c2336` → `var(--card-border)`
- `#101520`, `#0d1220` → `var(--bg-secondary)`
- `#060910` → `var(--bg-primary)`
- `#22c55e`, `#16a34a` → 유지 (시맨틱: 수익 그린)
- `#ef4444` → 유지 (시맨틱: 손실 레드)

- [ ] **Step 4: input 스타일 통일**

```css
/* before */ border-radius: 5px; padding: 6px 9px; border: 1px solid #1c2336;
/* after  */ border-radius: var(--input-radius); padding: var(--input-padding); border: 1px solid var(--input-border);
```

- [ ] **Step 5: pill/badge 통일**

```css
/* before */ .scalp-pill { border-radius: 4px; }
/* after  */ .scalp-pill { border-radius: var(--radius-full); }
```

- [ ] **Step 6: font-size 토큰 적용**

```css
/* before */ font-size: 13.5px;
/* after  */ font-size: var(--font-base);

/* before */ font-size: 9px;
/* after  */ font-size: var(--font-xs);
```

- [ ] **Step 7: Commit**

```bash
git add web/src/pages/ScalpAnalyzer.css
git commit -m "refactor: ScalpAnalyzer 하드코딩 색상 → CSS 변수 + 토큰 적용"
```

---

### Task 3: FabioStrategy.css 하드코딩 → CSS 변수

**Files:**
- Modify: `web/src/pages/FabioStrategy.css`

- [ ] **Step 1~6: ScalpAnalyzer와 동일 패턴으로 교체**

FabioStrategy는 ScalpAnalyzer와 거의 동일한 스타일 패턴 사용:
- `.fb-box` = `.scalp-box` 동일 교체
- `.fb-pill` = `.scalp-pill` 동일 교체
- 하드코딩 색상 동일 매핑
- input, font-size 동일 교체

- [ ] **Step 7: Commit**

```bash
git add web/src/pages/FabioStrategy.css
git commit -m "refactor: FabioStrategy 하드코딩 색상 → CSS 변수 + 토큰 적용"
```

---

## Chunk 3: 주요 페이지 토큰 적용

### Task 4: Dashboard.css 토큰 적용

**Files:**
- Modify: `web/src/pages/Dashboard.css`

- [ ] **Step 1: 검색 박스 radius 통일**

```css
/* before */ .search-box { border-radius: 12px; }
/* after  */ .search-box { border-radius: var(--card-radius); }
```

- [ ] **Step 2: metric 패딩 통일**

```css
/* before */ padding: 1.5rem;
/* after  */ padding: var(--card-padding);
```

- [ ] **Step 3: font-size 토큰 적용 (타이틀)**

```css
/* 2.5rem → var(--font-xl) to match other page titles */
```

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/Dashboard.css
git commit -m "refactor: Dashboard.css 디자인 토큰 적용"
```

---

### Task 5: Operations.css + 컴포넌트 CSS 토큰 적용

**Files:**
- Modify: `web/src/pages/Operations.css`
- Modify: `web/src/components/operations/OpsPerformanceCards.css`
- Modify: `web/src/components/operations/PositionTable.css`

- [ ] **Step 1: OpsPerformanceCards padding 통일**

```css
/* before */ padding: 12px 14px;
/* after  */ padding: var(--card-padding);
```

- [ ] **Step 2: PositionTable cell padding 통일**

```css
/* before */ padding: 8px 10px; / padding: 10px 10px;
/* after  */ padding: var(--table-cell-padding);
```

- [ ] **Step 3: border 색상 통일**

```css
/* before */ border-bottom: 1px solid rgba(255,255,255,0.06);
/* after  */ border-bottom: 1px solid var(--table-border);
```

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/Operations.css web/src/components/operations/OpsPerformanceCards.css web/src/components/operations/PositionTable.css
git commit -m "refactor: Operations 관련 CSS 디자인 토큰 적용"
```

---

### Task 6: Performance + Risk CSS 토큰 적용

**Files:**
- Modify: `web/src/pages/Performance.css`
- Modify: `web/src/pages/Risk.css`
- Modify: `web/src/components/performance/PerformanceMetrics.css`
- Modify: `web/src/components/risk/RiskGauge.css`

- [ ] **Step 1: PerformanceMetrics card padding 통일**

```css
/* before */ padding: 16px;
/* after  */ padding: var(--card-padding);
```

- [ ] **Step 2: RiskGauge card 토큰 적용**

- [ ] **Step 3: border/radius 통일**

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/Performance.css web/src/pages/Risk.css web/src/components/performance/PerformanceMetrics.css web/src/components/risk/RiskGauge.css
git commit -m "refactor: Performance/Risk CSS 디자인 토큰 적용"
```

---

### Task 7: Rebalance + Home + OptionCalculator + SignalOverview 토큰 적용

**Files:**
- Modify: `web/src/pages/Rebalance.css`
- Modify: `web/src/pages/Home.css`
- Modify: `web/src/pages/OptionCalculator.css`
- Modify: `web/src/pages/SignalOverview.css`

- [ ] **Step 1: Rebalance.css**

```css
/* backtest-metrics-grid: radius 12px → var(--card-radius), border rgba → var(--card-border) */
/* date input: radius 6px → var(--input-radius), padding → var(--input-padding) */
/* table: padding → var(--table-cell-padding) */
```

- [ ] **Step 2: Home.css**

```css
/* metric-card: border rgba(255,255,255,0.05) → var(--card-border) */
```

- [ ] **Step 3: OptionCalculator.css**

```css
/* input → var(--input-radius), var(--input-padding) */
/* card → var(--card-radius), var(--card-padding) */
```

- [ ] **Step 4: SignalOverview.css**

```css
/* signal-card: radius 16px → var(--card-radius) */
/* signal-card-features li: border → var(--card-border) */
```

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/Rebalance.css web/src/pages/Home.css web/src/pages/OptionCalculator.css web/src/pages/SignalOverview.css
git commit -m "refactor: Rebalance/Home/OptionCalc/SignalOverview 디자인 토큰 적용"
```

---

## Chunk 4: 검증

### Task 8: 빌드 + 시각적 검증

- [ ] **Step 1: TypeScript 체크**

Run: `cd web && npx tsc --noEmit`

- [ ] **Step 2: Vite 빌드**

Run: `cd web && npm run build`

- [ ] **Step 3: 개발 서버에서 각 페이지 시각적 확인**

확인 항목:
1. `/` — Home 카드 radius/padding 통일
2. `/signals` — SignalOverview 카드
3. `/signals/stocks` — Dashboard 차트/메트릭
4. `/signals/futures` — ScalpAnalyzer (하드코딩 제거 확인)
5. `/signals/futures/fabio` — FabioStrategy
6. `/signals/options` — OptionCalculator
7. `/trading/operations` — Operations 테이블/카드
8. `/trading/risk` — Risk 게이지
9. `/review/performance` — Performance 메트릭
10. `/review/rebalance` — Rebalance 테이블

- [ ] **Step 4: Final Commit (if any fixes needed)**
