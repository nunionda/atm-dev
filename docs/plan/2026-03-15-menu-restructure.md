# Menu Restructure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 8개 flat 메뉴를 워크플로우 기반 3-그룹 (Signal Lab / Trading / Review) 드롭다운 네비게이션으로 재구성

**Architecture:** React Router nested routes + dropdown Navbar. 기존 페이지 컴포넌트는 재사용하고 라우팅과 네비게이션만 변경. 신규 페이지는 SignalOverview(3자산 요약)와 BacktestPage(Rebalance에서 분리) 2개.

**Tech Stack:** React 19, React Router v6, TypeScript, Tailwind/CSS, lucide-react icons

**Spec:** `docs/superpowers/specs/2026-03-15-menu-restructure-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `web/src/components/layout/Navbar.tsx` | Rewrite | 3-그룹 드롭다운 메뉴 + 모바일 hamburger |
| `web/src/components/layout/Navbar.css` | Rewrite | 드롭다운 스타일, hover, active, 모바일 |
| `web/src/App.tsx` | Modify | 새 라우트 + legacy redirect |
| `web/src/pages/SignalOverview.tsx` | Create | 3자산 시그널 요약 랜딩 |
| `web/src/components/layout/SubNavigation.tsx` | Create | 공통 서브탭 네비게이션 |
| `web/src/pages/BacktestPage.tsx` | Create | BacktestSection wrapper |
| `web/src/pages/Rebalance.tsx` | Modify | BacktestSection import/render 제거 |
| `web/src/pages/ScalpAnalyzer.tsx` | Modify | Link 경로 업데이트 (line 861) |
| `web/src/pages/FabioStrategy.tsx` | Modify | Link 경로 업데이트 (line 377) |

---

## Chunk 1: Routing & Navigation Infrastructure

### Task 1: App.tsx 라우트 재구성

**Files:**
- Modify: `web/src/App.tsx`

- [ ] **Step 1: 새 라우트 구조로 App.tsx 수정**

```tsx
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Navbar } from './components/layout/Navbar';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AppStateProvider } from './contexts/AppStateContext';
import { Home } from './pages/Home';
import { Theory } from './pages/Theory';
import { Dashboard } from './pages/Dashboard';
import { Operations } from './pages/Operations';
import { Risk } from './pages/Risk';
import { Performance } from './pages/Performance';
import { ScalpAnalyzer } from './pages/ScalpAnalyzer';
import { FabioStrategy } from './pages/FabioStrategy';
import { OptionCalculator } from './pages/OptionCalculator';
import { Rebalance } from './pages/Rebalance';
import { SignalOverview } from './pages/SignalOverview';
import { BacktestPage } from './pages/BacktestPage';

function App() {
  return (
    <Router>
      <AppStateProvider>
      <Navbar />
      <ErrorBoundary>
        <Routes>
          {/* Home */}
          <Route path="/" element={<Home />} />

          {/* Signal Lab */}
          <Route path="/signals" element={<SignalOverview />} />
          <Route path="/signals/stocks" element={<Dashboard />} />
          <Route path="/signals/futures" element={<ScalpAnalyzer />} />
          <Route path="/signals/futures/fabio" element={<FabioStrategy />} />
          <Route path="/signals/options" element={<OptionCalculator />} />

          {/* Trading */}
          <Route path="/trading" element={<Navigate to="/trading/operations" replace />} />
          <Route path="/trading/operations" element={<Operations />} />
          <Route path="/trading/risk" element={<Risk />} />

          {/* Review */}
          <Route path="/review" element={<Navigate to="/review/performance" replace />} />
          <Route path="/review/performance" element={<Performance />} />
          <Route path="/review/backtest" element={<BacktestPage />} />
          <Route path="/review/rebalance" element={<Rebalance />} />

          {/* Theory */}
          <Route path="/theory/*" element={<Theory />} />

          {/* Legacy Redirects */}
          <Route path="/dashboard" element={<Navigate to="/signals/stocks" replace />} />
          <Route path="/scalp-analyzer/fabio" element={<Navigate to="/signals/futures/fabio" replace />} />
          <Route path="/scalp-analyzer" element={<Navigate to="/signals/futures" replace />} />
          <Route path="/option-calculator" element={<Navigate to="/signals/options" replace />} />
          <Route path="/operations" element={<Navigate to="/trading/operations" replace />} />
          <Route path="/risk" element={<Navigate to="/trading/risk" replace />} />
          <Route path="/performance" element={<Navigate to="/review/performance" replace />} />
          <Route path="/rebalance" element={<Navigate to="/review/rebalance" replace />} />
        </Routes>
      </ErrorBoundary>
      </AppStateProvider>
    </Router>
  );
}

export default App;
```

Note: `/scalp-analyzer/fabio` redirect must come before `/scalp-analyzer` to avoid matching order issues.

- [ ] **Step 2: TypeScript 타입 체크**

Run: `cd web && npx tsc --noEmit 2>&1 | head -20`
Expected: SignalOverview, BacktestPage 모듈 미존재 에러 (아직 생성 전이므로 정상)

- [ ] **Step 3: Commit**

```bash
git add web/src/App.tsx
git commit -m "refactor: 라우트 구조 변경 (Signal Lab / Trading / Review 3그룹 + legacy redirect)"
```

---

### Task 2: Navbar 드롭다운 재작성

**Files:**
- Rewrite: `web/src/components/layout/Navbar.tsx`
- Rewrite: `web/src/components/layout/Navbar.css`

- [ ] **Step 1: Navbar.tsx를 3-그룹 드롭다운 구조로 재작성**

```tsx
import { useState, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LineChart, Crosshair, Radio, Shield, BarChart3,
  Activity, Calculator, BookOpen, ChevronDown,
  LayoutDashboard, RefreshCw, FlaskConical, Menu, X
} from 'lucide-react';
import './Navbar.css';

interface NavGroup {
  label: string;
  prefix: string;
  items: { to: string; icon: React.ReactNode; label: string }[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Signal Lab',
    prefix: '/signals',
    items: [
      { to: '/signals', icon: <LayoutDashboard size={16} />, label: 'Overview' },
      { to: '/signals/stocks', icon: <LineChart size={16} />, label: 'Stocks' },
      { to: '/signals/futures', icon: <Activity size={16} />, label: 'Futures' },
      { to: '/signals/options', icon: <Calculator size={16} />, label: 'Options' },
    ],
  },
  {
    label: 'Trading',
    prefix: '/trading',
    items: [
      { to: '/trading/operations', icon: <Radio size={16} />, label: 'Operations' },
      { to: '/trading/risk', icon: <Shield size={16} />, label: 'Risk' },
    ],
  },
  {
    label: 'Review',
    prefix: '/review',
    items: [
      { to: '/review/performance', icon: <BarChart3 size={16} />, label: 'Performance' },
      { to: '/review/backtest', icon: <FlaskConical size={16} />, label: 'Backtest' },
      { to: '/review/rebalance', icon: <RefreshCw size={16} />, label: 'Rebalance' },
    ],
  },
];

export function Navbar() {
  const location = useLocation();
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null);

  const isGroupActive = (prefix: string) => location.pathname.startsWith(prefix);
  const isItemActive = (to: string) => location.pathname === to;

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpenGroup(null);
        setMobileOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close dropdown on route change
  useEffect(() => {
    setOpenGroup(null);
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <nav className="navbar glass-panel" ref={navRef}>
      <div className="nav-container container">
        <Link to="/" className="nav-logo">
          <div className="logo-icon">
            <Crosshair className="text-gradient" size={24} />
          </div>
          <span className="logo-text">ATS</span>
        </Link>

        {/* Mobile hamburger */}
        <button
          className="nav-mobile-toggle"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle menu"
        >
          {mobileOpen ? <X size={24} /> : <Menu size={24} />}
        </button>

        <div className={`nav-links ${mobileOpen ? 'nav-links--open' : ''}`}>
          <Link
            to="/"
            className={`nav-link ${location.pathname === '/' ? 'active' : ''}`}
          >
            Home
          </Link>

          {NAV_GROUPS.map((group) => (
            <div
              key={group.label}
              className={`nav-group ${isGroupActive(group.prefix) ? 'active' : ''}`}
              onMouseEnter={() => setOpenGroup(group.label)}
              onMouseLeave={() => setOpenGroup(null)}
            >
              <button
                className={`nav-link nav-group-trigger ${isGroupActive(group.prefix) ? 'active' : ''}`}
                onClick={() => setOpenGroup(openGroup === group.label ? null : group.label)}
              >
                <span>{group.label}</span>
                <ChevronDown
                  size={14}
                  className={`nav-chevron ${openGroup === group.label ? 'nav-chevron--open' : ''}`}
                />
              </button>

              {openGroup === group.label && (
                <div className="nav-dropdown glass-panel">
                  {group.items.map((item) => (
                    <Link
                      key={item.to}
                      to={item.to}
                      className={`nav-dropdown-item ${isItemActive(item.to) ? 'active' : ''}`}
                    >
                      {item.icon}
                      <span>{item.label}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Theory icon (right side) */}
        <div className="nav-actions">
          <Link
            to="/theory"
            className={`nav-link nav-theory ${isGroupActive('/theory') ? 'active' : ''}`}
            title="Documentation"
          >
            <BookOpen size={20} />
          </Link>
        </div>
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Navbar.css 드롭다운 스타일 작성**

```css
/* === Navbar Base === */
.navbar {
  position: sticky;
  top: 1.5rem;
  z-index: 100;
  margin: 1.5rem auto;
  padding: 0.5rem 0;
  border-radius: 100px;
  max-width: 1200px;
  width: calc(100% - 4rem);
}

.nav-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 1rem;
}

.nav-logo {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-weight: 700;
  font-size: 1.15rem;
  letter-spacing: -0.02em;
}

.logo-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
}

.logo-text {
  color: var(--text-primary);
}

/* === Nav Links === */
.nav-links {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-secondary);
  padding: 0.5rem 1rem;
  border-radius: 100px;
  transition: all var(--transition-fast);
  background: none;
  border: none;
  cursor: pointer;
  white-space: nowrap;
}

.nav-link:hover,
.nav-link.active {
  color: var(--text-primary);
}

.nav-link.active {
  background: var(--border-light);
}

/* === Group & Dropdown === */
.nav-group {
  position: relative;
}

.nav-group-trigger {
  font-family: inherit;
}

.nav-chevron {
  transition: transform var(--transition-fast);
}

.nav-chevron--open {
  transform: rotate(180deg);
}

.nav-dropdown {
  position: absolute;
  top: calc(100% + 0.5rem);
  left: 50%;
  transform: translateX(-50%);
  min-width: 180px;
  padding: 0.5rem;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  z-index: 200;
  animation: dropdown-in 0.15s ease-out;
}

@keyframes dropdown-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-4px); }
  to   { opacity: 1; transform: translateX(-50%) translateY(0); }
}

.nav-dropdown-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 1rem;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-secondary);
  border-radius: 8px;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.nav-dropdown-item:hover {
  background: var(--border-light);
  color: var(--text-primary);
}

.nav-dropdown-item.active {
  background: var(--border-light);
  color: var(--text-primary);
  font-weight: 600;
}

/* === Theory icon === */
.nav-theory {
  padding: 0.5rem;
  border-radius: 50%;
}

/* === Actions === */
.nav-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

/* === Mobile === */
.nav-mobile-toggle {
  display: none;
  background: none;
  border: none;
  color: var(--text-primary);
  cursor: pointer;
  padding: 0.5rem;
}

@media (max-width: 768px) {
  .navbar {
    border-radius: 16px;
    top: 0.5rem;
    margin: 0.5rem;
    width: calc(100% - 1rem);
  }

  .nav-mobile-toggle {
    display: flex;
  }

  .nav-links {
    display: none;
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 0;
    right: 0;
    flex-direction: column;
    padding: 1rem;
    border-radius: 16px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow-lg);
    gap: 0.25rem;
  }

  .nav-links--open {
    display: flex;
  }

  .nav-group {
    width: 100%;
  }

  .nav-group-trigger {
    width: 100%;
    justify-content: space-between;
  }

  .nav-dropdown {
    position: static;
    transform: none;
    box-shadow: none;
    border: none;
    padding: 0 0 0 1rem;
    animation: none;
  }

  @keyframes dropdown-in {
    from { opacity: 1; transform: none; }
    to   { opacity: 1; transform: none; }
  }
}
```

- [ ] **Step 3: 개발 서버에서 Navbar 렌더링 확인**

Run: `cd web && npx tsc --noEmit 2>&1 | head -20`
Expected: SignalOverview, BacktestPage import 에러만 (아직 미생성)

- [ ] **Step 4: Commit**

```bash
git add web/src/components/layout/Navbar.tsx web/src/components/layout/Navbar.css
git commit -m "feat: Navbar 3-그룹 드롭다운 재작성 (Signal Lab / Trading / Review + 모바일 hamburger)"
```

---

## Chunk 2: 신규 페이지 & 컴포넌트

### Task 3: SubNavigation 공통 컴포넌트

**Files:**
- Create: `web/src/components/layout/SubNavigation.tsx`

- [ ] **Step 1: SubNavigation 컴포넌트 작성**

이 컴포넌트는 각 그룹 내부 페이지에서 서브탭을 표시. Signal Lab 페이지에서는 자산군 탭 + 자산별 서브탭 2줄, Trading/Review에서는 서브탭 1줄.

```tsx
import { Link, useLocation } from 'react-router-dom';

export interface SubNavTab {
  to: string;
  label: string;
}

interface SubNavigationProps {
  tabs: SubNavTab[];
  className?: string;
}

export function SubNavigation({ tabs, className = '' }: SubNavigationProps) {
  const location = useLocation();

  return (
    <div className={`sub-nav ${className}`}>
      {tabs.map((tab) => (
        <Link
          key={tab.to}
          to={tab.to}
          className={`sub-nav-tab ${location.pathname === tab.to ? 'sub-nav-tab--active' : ''}`}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}
```

Add styles to `web/src/components/layout/Navbar.css` (append):

```css
/* === Sub Navigation === */
.sub-nav {
  display: flex;
  gap: 0.25rem;
  padding: 0.25rem;
  background: var(--bg-secondary);
  border-radius: 10px;
  border: 1px solid var(--border-color);
  width: fit-content;
}

.sub-nav-tab {
  padding: 0.4rem 1rem;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-secondary);
  border-radius: 8px;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.sub-nav-tab:hover {
  color: var(--text-primary);
}

.sub-nav-tab--active {
  background: var(--bg-primary);
  color: var(--text-primary);
  font-weight: 600;
  box-shadow: var(--shadow-sm);
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/layout/SubNavigation.tsx web/src/components/layout/Navbar.css
git commit -m "feat: SubNavigation 공통 서브탭 컴포넌트"
```

---

### Task 4: SignalOverview 페이지

**Files:**
- Create: `web/src/pages/SignalOverview.tsx`

- [ ] **Step 1: SignalOverview 페이지 작성**

3개 자산군(Stocks/Futures/Options) 시그널 요약 카드를 보여주는 랜딩 페이지.
기존 API (`/analyze/{ticker}`, `fetchQuote`) 조합으로 데이터 제공. 초기에는 정적 카드 + 링크로 시작.

```tsx
import { Link } from 'react-router-dom';
import { LineChart, Activity, Calculator, ArrowRight, TrendingUp } from 'lucide-react';
import './SignalOverview.css';

const ASSET_CARDS = [
  {
    title: 'Stocks',
    icon: <LineChart size={28} />,
    to: '/signals/stocks',
    description: '기술적 분석 & 시그널 스캐너',
    features: ['차트 분석', '진입 시그널', '마켓 레짐'],
    color: 'var(--accent-blue, #3b82f6)',
  },
  {
    title: 'Futures',
    icon: <Activity size={28} />,
    to: '/signals/futures',
    description: 'Z-Score & ATR 기반 선물 분석',
    features: ['스캘핑 분석', 'Fabio 전략', 'MTF 분석'],
    color: 'var(--accent-green, #22c55e)',
  },
  {
    title: 'Options',
    icon: <Calculator size={28} />,
    to: '/signals/options',
    description: 'Black-Scholes 옵션 가격 계산',
    features: ['BS 계산기', '그릭스', '프리셋 자산'],
    color: 'var(--accent-purple, #a855f7)',
  },
];

export function SignalOverview() {
  return (
    <div className="signal-overview">
      <div className="signal-overview-header">
        <div className="signal-overview-title">
          <TrendingUp size={28} />
          <h1>Signal Lab</h1>
        </div>
        <p className="signal-overview-subtitle">
          주식 · 선물 · 옵션 매매 신호 분석 & 진입 전략
        </p>
      </div>

      <div className="signal-overview-grid">
        {ASSET_CARDS.map((card) => (
          <Link key={card.title} to={card.to} className="signal-card glass-panel">
            <div className="signal-card-icon" style={{ color: card.color }}>
              {card.icon}
            </div>
            <h2 className="signal-card-title">{card.title}</h2>
            <p className="signal-card-desc">{card.description}</p>
            <ul className="signal-card-features">
              {card.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <div className="signal-card-action" style={{ color: card.color }}>
              <span>상세 보기</span>
              <ArrowRight size={16} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: SignalOverview.css 작성**

```css
.signal-overview {
  max-width: 1200px;
  margin: 2rem auto;
  padding: 0 2rem;
}

.signal-overview-header {
  text-align: center;
  margin-bottom: 3rem;
}

.signal-overview-title {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.signal-overview-title h1 {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
}

.signal-overview-subtitle {
  color: var(--text-secondary);
  font-size: 1.1rem;
}

.signal-overview-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
}

.signal-card {
  padding: 2rem;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
  cursor: pointer;
}

.signal-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.signal-card-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--bg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.signal-card-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
}

.signal-card-desc {
  font-size: 0.9rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.signal-card-features {
  list-style: none;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.5rem 0;
}

.signal-card-features li {
  font-size: 0.8rem;
  padding: 0.25rem 0.75rem;
  background: var(--bg-secondary);
  border-radius: 100px;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
}

.signal-card-action {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  font-weight: 600;
  margin-top: auto;
}

@media (max-width: 768px) {
  .signal-overview-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 3: TypeScript 타입 체크**

Run: `cd web && npx tsc --noEmit 2>&1 | head -20`
Expected: BacktestPage 관련 에러만 남음

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/SignalOverview.tsx web/src/pages/SignalOverview.css
git commit -m "feat: SignalOverview 3자산 시그널 요약 랜딩 페이지"
```

---

### Task 5: BacktestPage 생성

**Files:**
- Create: `web/src/pages/BacktestPage.tsx`

- [ ] **Step 1: BacktestPage 작성 — BacktestSection wrapper**

```tsx
import { BacktestSection } from '../components/rebalance/BacktestSection';
import { SubNavigation } from '../components/layout/SubNavigation';
import { useAppState } from '../contexts/AppStateContext';

const REVIEW_TABS = [
  { to: '/review/performance', label: 'Performance' },
  { to: '/review/backtest', label: 'Backtest' },
  { to: '/review/rebalance', label: 'Rebalance' },
];

export function BacktestPage() {
  const { activeMarket } = useAppState();

  return (
    <div style={{ maxWidth: 1200, margin: '2rem auto', padding: '0 2rem' }}>
      <SubNavigation tabs={REVIEW_TABS} />
      <div style={{ marginTop: '1.5rem' }}>
        <BacktestSection activeMarket={activeMarket} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript 타입 체크**

Run: `cd web && npx tsc --noEmit 2>&1 | head -20`
Expected: 에러 없음 (모든 import 해결됨)

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/BacktestPage.tsx
git commit -m "feat: BacktestPage — Rebalance에서 분리된 독립 백테스트 페이지"
```

---

## Chunk 3: 기존 페이지 수정

### Task 6: Rebalance에서 BacktestSection 제거

**Files:**
- Modify: `web/src/pages/Rebalance.tsx` (line 5: import 제거, line 123: render 제거)

- [ ] **Step 1: BacktestSection import 및 render 제거**

`web/src/pages/Rebalance.tsx`에서:

1. Line 5: `import { BacktestSection } ...` 삭제
2. Line 123: `<BacktestSection activeMarket={activeMarket} />` 삭제

- [ ] **Step 2: TypeScript 체크**

Run: `cd web && npx tsc --noEmit 2>&1 | head -5`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/Rebalance.tsx
git commit -m "refactor: Rebalance에서 BacktestSection 분리 (BacktestPage로 이동)"
```

---

### Task 7: ScalpAnalyzer & FabioStrategy 내부 Link 업데이트

**Files:**
- Modify: `web/src/pages/ScalpAnalyzer.tsx` (line 861)
- Modify: `web/src/pages/FabioStrategy.tsx` (line 377)

- [ ] **Step 1: ScalpAnalyzer.tsx Link 경로 변경**

Line 861: `to="/scalp-analyzer/fabio"` → `to="/signals/futures/fabio"`

- [ ] **Step 2: FabioStrategy.tsx Link 경로 변경**

Line 377: `to="/scalp-analyzer"` → `to="/signals/futures"`

- [ ] **Step 3: Link 경로 확인 (전체 검색)**

Run: `cd web && grep -rn 'scalp-analyzer\|/operations"\|/risk"\|/performance"\|/rebalance"\|/dashboard"' src/pages/ src/components/ --include='*.tsx' | grep -v node_modules`

Expected: 더 이상 old route를 직접 참조하는 Link가 없어야 함. AppStateContext의 `navigateToOperations` 같은 프로그래밍 방식 네비게이션도 확인 필요.

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/ScalpAnalyzer.tsx web/src/pages/FabioStrategy.tsx
git commit -m "fix: ScalpAnalyzer/FabioStrategy 내부 Link 경로를 새 라우트로 업데이트"
```

---

### Task 8: AppStateContext navigateToOperations 경로 업데이트

**Files:**
- Modify: `web/src/contexts/AppStateContext.tsx` (if it references `/operations`)

- [ ] **Step 1: AppStateContext에서 old route 참조 확인**

Run: `cd web && grep -n '/operations\|/risk\|/dashboard\|/performance\|/rebalance' src/contexts/AppStateContext.tsx`

If found: `/operations` → `/trading/operations` 등으로 변경.

- [ ] **Step 2: 전체 코드에서 old route 하드코딩 검색**

Run: `cd web && grep -rn '"/operations"\|"/risk"\|"/dashboard"\|"/performance"\|"/rebalance"\|"/scalp-analyzer"\|"/option-calculator"' src/ --include='*.tsx' --include='*.ts' | grep -v App.tsx | grep -v node_modules`

나온 결과에 대해 모두 새 경로로 수정.

- [ ] **Step 3: Commit**

```bash
git add -u web/src/
git commit -m "fix: 전체 코드베이스에서 old route 참조를 새 라우트로 업데이트"
```

---

## Chunk 4: 검증 & 마무리

### Task 9: TypeScript 빌드 검증

- [ ] **Step 1: TypeScript 전체 타입 체크**

Run: `cd web && npx tsc --noEmit`
Expected: 에러 0

- [ ] **Step 2: Vite 프로덕션 빌드**

Run: `cd web && npm run build`
Expected: 빌드 성공

- [ ] **Step 3: Commit (빌드 통과 확인)**

빌드에 문제 없으면 별도 커밋 불필요. 문제 있으면 수정 후 커밋.

---

### Task 10: 개발 서버 동작 검증

- [ ] **Step 1: 개발 서버 시작**

Run: `cd web && npm run dev`

- [ ] **Step 2: 주요 라우트 동작 확인**

확인 항목:
1. `/` — Home 렌더링
2. `/signals` — SignalOverview 3카드
3. `/signals/stocks` — Dashboard (기존 차트)
4. `/signals/futures` — ScalpAnalyzer
5. `/signals/futures/fabio` — FabioStrategy
6. `/signals/options` — OptionCalculator
7. `/trading/operations` — Operations
8. `/trading/risk` — Risk
9. `/review/performance` — Performance
10. `/review/backtest` — BacktestPage
11. `/review/rebalance` — Rebalance (BacktestSection 없음)

- [ ] **Step 3: Legacy redirect 확인**

확인 항목:
1. `/dashboard` → `/signals/stocks` 자동 이동
2. `/scalp-analyzer` → `/signals/futures`
3. `/operations` → `/trading/operations`
4. `/rebalance` → `/review/rebalance`

- [ ] **Step 4: Navbar 드롭다운 확인**

확인 항목:
1. Signal Lab hover → 드롭다운 (Overview, Stocks, Futures, Options)
2. Trading hover → 드롭다운 (Operations, Risk)
3. Review hover → 드롭다운 (Performance, Backtest, Rebalance)
4. 현재 페이지 그룹 active 하이라이트
5. Theory 아이콘 우측 표시

---

## Implementation Notes

- **Task 1-2**: 라우팅 + Navbar 변경 (SignalOverview/BacktestPage 없이는 일부 라우트 에러 — Task 4-5에서 해결)
- **Task 3-5**: 신규 컴포넌트 (Task 5 완료 시 tsc 에러 0)
- **Task 6-8**: 기존 코드 정리
- **Task 9-10**: 전체 검증
- SubNavigation은 이번 구현에서 BacktestPage에만 적용. Dashboard/ScalpAnalyzer/OptionCalculator의 서브탭은 향후 별도 태스크로 진행 (이번 scope은 네비게이션 구조 변경에 집중)
