# ATS 코딩 컨벤션 가이드

> LLM이 이 프로젝트의 코드를 작성할 때 반드시 따라야 할 코딩 스타일과 패턴.
> 프로젝트 구조, 전략 스펙, 비즈니스 룰은 `CLAUDE.md` 참조.

---

## 1. Python 백엔드

### 네이밍

| 대상 | 규칙 | 예시 |
|------|------|------|
| 변수, 함수 | snake_case | `stock_code`, `check_risk_gates()` |
| 클래스 | PascalCase | `MomentumSwingStrategy`, `RiskManager` |
| 상수, Enum 값 | SCREAMING_SNAKE_CASE | `INIT`, `READY`, `RUNNING` |
| 파일 | snake_case | `main_loop.py`, `risk_manager.py` |
| 프라이빗 | `_` 접두사 (필요 시) | `_daily_loss_triggered` |

### 임포트 순서

```python
# 1. Future annotations (항상 최상단)
from __future__ import annotations

# 2. 표준 라이브러리
from datetime import datetime
from typing import Optional, List, Dict

# 3. 서드파티
import pandas as pd
import numpy as np
from sqlalchemy import Column, Float

# 4. 로컬 모듈 (도메인 기반)
from common.enums import SystemState, ExitReason
from common.types import Signal, ExitSignal
from data.config_manager import ATSConfig
from infra.logger import get_logger
```

- `from module import *` 절대 금지
- 배치 임포트: 같은 모듈에서 여러 항목 가져올 때 한 줄로

### 타입 힌트

```python
# 모든 함수 인자와 리턴 타입 명시
def scan_entry_signals(
    self,
    universe_codes: List[str],
    ohlcv_data: dict[str, pd.DataFrame],
    current_prices: dict,
) -> List[Signal]:
    ...

# Optional 명시적 사용
def get_position(self, code: str) -> Optional[Position]:
    ...
```

### 도메인 객체 — `@dataclass`

```python
@dataclass
class Signal:
    stock_code: str
    stock_name: str
    signal_type: str = "BUY"
    primary_signals: List[str] = field(default_factory=list)
    strength: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
```

- 모든 도메인 값 객체는 `@dataclass`로 정의
- 가변 기본값은 `field(default_factory=...)` 사용
- 파생 필드는 `__post_init__`에서 처리

### Config 접근 패턴

```python
class MomentumSwingStrategy(BaseStrategy):
    def __init__(self, config: ATSConfig):
        self.config = config
        self.sc = config.strategy    # 단축 접근
        self.ec = config.exit
        self.pc = config.portfolio
```

- Config는 생성자 주입 (글로벌 상태 금지)
- 매직 넘버 금지 — 모든 파라미터는 `config.yaml`에서 관리
- 단축 별칭: `self.sc`, `self.ec`, `self.pc` 등

### 에러 처리 — Result 객체 패턴

```python
@dataclass
class RiskCheckResult:
    passed: bool
    failed_gate: Optional[str] = None
    reason: Optional[str] = None

# 사용
result = risk_mgr.check_risk_gates(signal, portfolio)
if not result.passed:
    logger.info("RG1 FAIL | %s | %s", signal.stock_code, result.reason)
```

- 예외 대신 Result 객체로 실패 사유 전달
- try-except는 초기화/외부 API 호출 등 경계에서만 사용

### 로깅

```python
logger = get_logger("module_name")  # 파일 상단, 모듈별 1개

# percent-format 선호 (f-string 아님)
logger.info("RG1 FAIL | %s | daily_loss=%.2f%%", code, pct * 100)
logger.critical("MDD limit reached: %.2f%%", mdd * 100)
```

| 레벨 | 용도 |
|------|------|
| `info` | 운영 마일스톤 (시그널 발견, 게이트 통과, 포지션 오픈) |
| `debug` | 상세 계산 과정 |
| `warning` | 복구 가능한 문제 |
| `critical` | 하드 스톱 (일일 손실 한도, MDD 한도) |

### Docstring 스타일

```python
"""
매매 메인 루프
문서: ATS-SAD-001 §5.7

장중 매매의 핵심 루프:
  Phase 1: 포지션 모니터링 (UC-04)
  Phase 2: 일일 손실 한도 체크 (BR-R01)
"""

class RiskManager:
    """
    리스크 게이트와 한도를 관리한다.
    모든 매수 주문 전에 check_risk_gates()를 호출해야 한다.
    """

    def check_risk_gates(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """리스크 게이트 RG1~RG4를 순차 체크한다 (BRD §2.3.3)."""
```

- 한국어 작성
- 내부 문서 참조 포함 (BRD §2.3, SAD §5.7)
- 간결하게 — 목적과 리턴값 중심

### 코드 구조

```python
class MyClass:
    """Docstring."""

    def __init__(self, config: ATSConfig):
        self.config = config

    # ══════════════════════════════════════════
    # 지표 계산
    # ══════════════════════════════════════════

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        ...

    # ══════════════════════════════════════════
    # 시그널 스캔
    # ══════════════════════════════════════════

    def scan_entry_signals(self, ...) -> List[Signal]:
        ...
```

- `# ══════` 디바이더로 논리적 섹션 구분
- 가드 절을 메서드 상단에 배치:
  ```python
  if df.empty or len(df) < self.sc.ma_long:
      return df
  ```

### pandas 패턴

```python
c = df["close"].astype(float)
v = df["volume"].astype(float)
df["ma_short"] = c.rolling(window=self.sc.ma_short).mean()
df["rsi"] = 100 - (100 / (1 + rs))
```

- 컬럼 접근 시 `.astype(float)` 안전 변환
- `.rolling()` 체인 사용
- 단축 변수: `c = df["close"]`, `v = df["volume"]`

### 전략 확장

```python
class NewStrategy(BaseStrategy):
    def __init__(self, config: ATSConfig):
        self.config = config

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """지표 계산 구현."""
        ...

    def scan_entry_signals(self, universe_codes, ohlcv_data, current_prices) -> List[Signal]:
        """진입 시그널 스캔 구현."""
        ...

    def scan_exit_signals(self, positions, ohlcv_data, current_prices) -> List[ExitSignal]:
        """청산 시그널 스캔 구현."""
        ...
```

- `BaseStrategy` ABC의 3개 추상 메서드 구현 필수
- 전략은 시그널 생성만 담당 (실행은 별도 모듈)
- Signal, ExitSignal 도메인 객체 리턴

---

## 2. React/TypeScript 프론트엔드

### 컴포넌트 구조

```typescript
import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, Clock } from 'lucide-react';
import type { Position, MarketId } from '../../lib/api';
import { fetchPositions } from '../../lib/api';
import { useSSE } from '../../hooks/useSSE';
import './PositionTable.css';

interface Props {
    market: MarketId;
    onSelectTicker?: (symbol: string) => void;
}

export function PositionTable({ market, onSelectTicker }: Props) {
    const [positions, setPositions] = useState<Position[]>([]);
    // ...
    return (<div className="position-table-wrapper">...</div>);
}
```

- Functional 컴포넌트 only
- `interface Props` 인라인 정의 (컴포넌트 바로 위)
- Named export (`export function`, `export default` 아님)
- Optional props: `?:` 구문

### 파일 네이밍

| 대상 | 규칙 | 예시 |
|------|------|------|
| 컴포넌트 | PascalCase | `PositionTable.tsx`, `SignalAnalysis.tsx` |
| CSS | 컴포넌트와 동일 | `PositionTable.css` |
| 유틸/훅 | camelCase | `api.ts`, `useSSE.ts`, `signalEngine.ts` |
| 페이지 | PascalCase | `Operations.tsx`, `Risk.tsx` |

### 임포트 순서

```typescript
// 1. React hooks
import { useState, useEffect, useCallback, useRef } from 'react';

// 2. 아이콘 (lucide-react)
import { TrendingUp, TrendingDown, ShieldAlert } from 'lucide-react';

// 3. 타입 + API 함수
import type { Position, MarketId } from '../../lib/api';
import { fetchPositions, getMarketConfig } from '../../lib/api';

// 4. 커스텀 훅
import { useSSE } from '../../hooks/useSSE';

// 5. 자식/형제 컴포넌트
import { OpsRiskGauges } from '../components/operations/OpsRiskGauges';

// 6. 스타일 (항상 마지막)
import './ComponentName.css';
```

- `import type {}` 으로 타입과 런타임 임포트 구분
- 상대 경로 사용 (barrel export 없음)

### 상태 관리

```typescript
// 단순 상태
const [positions, setPositions] = useState<Position[]>([]);
const [loading, setLoading] = useState(true);

// 복잡 상태 → useReducer
interface ChartState { chartType: ChartType; activeSubcharts: {...}; }
type ChartAction = { type: 'SET_CHART_TYPE'; payload: ChartType } | ...;
const [chartState, dispatch] = useReducer(chartReducer, initialChartState);

// 비동기 데이터 로딩 → mounted 패턴
useEffect(() => {
    let mounted = true;
    async function loadData() {
        const result = await fetchPositions(market);
        if (mounted) setPositions(result);
    }
    loadData();
    return () => { mounted = false; };
}, [market]);
```

### SSE + REST 폴백

```typescript
// SSE 우선, REST 폴백
const sseData = useSSE<Position[]>(`${market}:positions`, () => fetchPositions(market));

useEffect(() => {
    fetchPositions(market).then(setPositions).catch(() => {});
}, [market]);

const displayData = sseData || positions;
```

- `useSSE<T>()` — 싱글톤 EventSource, 자동 재연결 (지수 백오프)
- SSE 실패 시 30초 REST 폴링 자동 전환
- 이벤트 키: `${market}:${eventType}` (예: `kospi:positions`)

### API 호출

```typescript
export async function fetchAnalyticsData(
    ticker: string,
    period: string = 'ytd',
    interval: string = '1d'
): Promise<AnalyticsResponse> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
        const response = await fetch(`${API_BASE_URL}/analyze/${ticker}?...`, {
            signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    } finally {
        clearTimeout(timeout);
    }
}
```

- 모든 API 함수는 `/lib/api.ts`에 집중
- AbortController로 타임아웃 처리
- 실패 시 graceful fallback (`return []` 또는 `return null`)

### CSS

```css
/* 일반 CSS 파일 사용 (CSS Modules, Tailwind 사용 안 함) */
.position-table-wrapper { ... }
.section-header { ... }
.count-badge { ... }

/* 상태 기반 클래스 */
.positive { color: var(--color-profit); }
.negative { color: var(--color-loss); }

/* 숫자 컬럼 */
.num { text-align: right; }
```

- 컴포넌트와 1:1 매칭되는 CSS 파일
- 글로벌 유틸 클래스: `.glass-panel`, `.loading-placeholder`, `.text-profit`, `.text-loss`
- CSS 변수 사용: `var(--text-primary)`, `var(--color-profit)`
- BEM-like 네이밍: `.position-table-wrapper`, `.section-header`

### 조건부 렌더링

```typescript
{loading && !sseData && <div className="loading-placeholder">Loading...</div>}
{displayData && (
    <table>
        {displayData.map(item => (
            <tr key={item.id}>...</tr>
        ))}
    </table>
)}
```

### 마켓 설정 참조

```typescript
import { getMarketConfig } from '../../lib/api';
const config = getMarketConfig(market);
// config.currency, config.currencySymbol, config.flag
```

---

## 3. 공통 원칙

### 아키텍처 레이어

```
Orchestrator (core/, simulation/)  — 흐름 제어
     ↓
Domain (strategy/, risk/, order/) — 비즈니스 로직
     ↓
Infrastructure (infra/broker/, infra/db/) — 외부 연동
```

- 상위 레이어만 하위 레이어를 호출 (역방향 의존 금지)
- 전략 클래스는 시그널만 생성, 주문 실행은 별도 모듈

### 설정 관리

- 모든 전략 파라미터는 `config.yaml`에서 관리
- 코드에 매직 넘버 직접 작성 금지
- `.env`에 시크릿 관리 (커밋 금지)

### 테스트

```python
# 네이밍: test_<기능>_<시나리오>_<기대결과>
def test_rg1_max_positions_fail(self, config, base_portfolio):
    """RG1: 최대 포지션 초과 시 거부."""
    ...

# Fixture로 공유 설정
@pytest.fixture
def config() -> ATSConfig:
    """테스트용 ATSConfig."""
    return ATSConfig(system_name="ATS-Test", ...)
```

- pytest 사용
- Fixture로 Config, Portfolio 등 공유 객체 제공
- 단순 assert 사용: `assert result.passed is True`

### 언어 규칙

- **코드**: 영어 (변수명, 함수명, 클래스명)
- **주석/문서**: 한국어
- **로그 메시지**: 영어 키워드 + 한국어 혼용 가능

---

## 4. 안티패턴 (하지 말 것)

| 금지 | 대신 |
|------|------|
| 글로벌 상태 / 싱글톤 Config | 생성자 주입 |
| `from module import *` | 명시적 임포트 |
| 매직 넘버 하드코딩 | `config.yaml` 참조 |
| CSS-in-JS, Tailwind | 일반 CSS 파일 |
| `export default` | Named export |
| 과도한 추상화 (1회용 헬퍼) | 인라인 구현 |
| 불필요한 try-except | Result 객체 패턴 |
| f-string 로깅 | percent-format 로깅 |
| `React.memo()` 남용 | 필요 시에만 최적화 |
| barrel export (`index.ts`) | 직접 파일 경로 임포트 |
