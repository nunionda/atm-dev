# 백엔드 코드리뷰

> 대상: `ats/` 전체 Python 모듈
> 리뷰 일자: 2026-03-14

---

## CRITICAL (4건) — 즉시 수정 필요

### C1. `main.py:28-42` — 존재하지 않는 모듈 import

```python
# main.py:28-42 — 아래 13개 모듈 중 다수가 미구현
from core.main_loop import MainLoop           # ❌ 미존재
from core.scheduler import Scheduler          # ❌ 미존재
from infra.broker.kis_broker import KISBroker  # ❌ 미존재
from infra.db.connection import Database       # ❌ 미존재
from infra.logger import setup_logger          # ❌ 미존재
from order.order_executor import OrderExecutor # ❌ 미존재
from position.position_manager import PositionManager  # ❌ 미존재
from report.report_generator import ReportGenerator    # ❌ 미존재
```

**영향**: `python main.py start` 실행 시 `ModuleNotFoundError` 즉시 발생. API 서버(`cmd_api`)만 정상 동작.

**수정**: 미구현 모듈은 stub 생성 or conditional import + 경고 로그.

---

### C2. `config_manager.py:226-239` — YAML 로딩 sp500_futures만 작동

```python
# config_manager.py:232-236
if "sp500_futures" in data:
    fc = data["sp500_futures"]
    for k, v in fc.items():
        if hasattr(config.sp500_futures, k):
            setattr(config.sp500_futures, k, v)
# ← strategy, exit, portfolio, risk, smc_strategy, breakout_retest 등 미로딩!
```

**영향**: `config.yaml` 수정해도 sp500_futures 외 전략에는 아무 효과 없음. 모든 전략이 하드코딩 기본값으로 동작.

**수정**: 모든 섹션에 대해 동일 패턴 적용 → `04-config-audit.md` 참조.

---

### C3. `config_manager.py:237-238` — FileNotFoundError 무시

```python
except FileNotFoundError:
    pass  # ← 경고 없이 기본값 사용
```

**영향**: config.yaml이 없어도 아무 에러 없이 기본값으로 시스템 시작. 프로덕션에서 설정 오류 감지 불가.

**수정**: `logger.warning("config.yaml not found, using defaults")` 추가 최소.

---

### C4. `config_manager.py:222-224` — .env 미로딩

```python
def __init__(self, config_path="config.yaml", env_path=".env"):
    self.config_path = config_path
    self.env_path = env_path  # ← env_path를 받지만 사용하지 않음
```

**영향**: KIS API 키, Telegram 토큰 등 시크릿이 로딩되지 않아 브로커/알림 연동 불가.

**수정**: `python-dotenv` 활용하여 `.env` 로딩 + `ATSConfig` 시크릿 필드 채우기.

---

## MAJOR (12건) — 백테스트/프로덕션 전 수정

### M1. `sp500_futures.py:50-57` — FuturesPositionState 초기값 문제

```python
highest_since_entry: float = 0.0         # 롱 진입 시 즉시 0 < entry_price → 트레일링 오작동
lowest_since_entry: float = float("inf") # 숏 진입 시 inf → 샹들리에 계산 오류 가능
```

**수정**: 진입 시 `highest = entry_price`, `lowest = entry_price`로 초기화.

---

### M2. `sp500_futures.py` — Position state 인메모리 only

`FuturesPositionState`가 dict로만 관리됨 (`self.position_states: Dict`). 프로세스 재시작 시 모든 트레일링/샹들리에 상태 소실.

**수정**: DB 모델에 `futures_position_state` 테이블 추가, 진입/청산 시 persist.

---

### M3. `sp500_futures.py:122-154` — NaN/Inf 전파 가능성

RSI 계산에서 `avg_loss = 0`일 때 Division by Zero, BB width에서 `sma = 0`일 때 무한대 등.
코드 내 명시적 NaN 체크가 부족하며, `float(curr.get("rsi", 50))` 식으로 기본값 대체 시 사일런트 오류.

**수정**: 지표 계산 후 `np.isnan()`/`np.isinf()` 체크 + 로깅.

---

### M4. `sp500_futures.py:457-659` — 100+ 하드코딩 매직넘버

4-Layer 스코어링 함수 전체에 걸쳐 임계값이 하드코딩:

```python
# Layer 1 (line ~457-488)
if abs_z >= 2.5:  score += 25     # 하드코딩
elif abs_z >= 2.0: score += 20    # 하드코딩
elif abs_z >= 1.5: score += 12    # 하드코딩

# Layer 2 (line ~513-548)
if adx > 40: score += 8          # config의 adx_strong 미사용
```

**영향**: 백테스트 파라미터 최적화 불가. config.yaml 수정해도 스코어링 로직 변경 불가.

**수정**: `SP500FuturesConfig`에 스코어링 티어별 파라미터 추가.

---

### M5. `sp500_futures.py:742-743` — ATR 0 폴백 하드코딩

```python
if atr <= 0:
    atr = entry_price * 0.01  # fallback: 1% — 이 값의 근거 불명
```

**수정**: config에 `atr_fallback_pct` 파라미터 추가.

---

### M6. `sp500_futures.py:696-698` — Volume ratio 임계값

```python
vol_ratio = float(curr.get("volume", 0)) / max(float(curr.get("volume_ma20", 1)), 1)
if vol_ratio < 0.8:  # 하드코딩 0.8 — config 무시
    return False
```

**수정**: `self.fc.volume_confirm_mult`와 별도의 `volume_min_ratio` config 필요.

---

### M7. `sp500_futures.py:1027-1030` — 트레일링 멀티플라이어 하드코딩

```python
if pnl_pct >= 0.06:
    trail_mult = max(1.0, trail_mult - 0.5)
elif pnl_pct >= 0.04:
    trail_mult = max(1.2, trail_mult - 0.3)
```

CLAUDE.md의 Progressive Trailing Stop 사양 (4-tier: ≥15%, ≥10%, ≥7%, default)과 완전 불일치.

**수정**: config에 `trailing_tiers` 리스트 추가, CLAUDE.md 사양 반영.

---

### M8. `config_manager.py:232-236` — 9개 설정 섹션 중 1개만 로딩

config.yaml에 정의된 `strategy`, `exit`, `portfolio`, `risk`, `order`, `smc_strategy`, `breakout_retest`, `mean_reversion`, `arbitrage` 섹션이 모두 무시됨.

→ `04-config-audit.md`에서 상세 분석.

---

### M9. `config_manager.py:234-236` — 타입 검증 없음

```python
setattr(config.sp500_futures, k, v)  # v가 문자열이면 float 필드에 str 할당
```

YAML에서 `"true"` (문자열) vs `true` (bool) 같은 파싱 차이로 런타임 에러 가능.

**수정**: `dataclass` 필드 타입 기반 자동 캐스팅 or Pydantic 전환.

---

### M10. `main.py:67-77` — KIS 시크릿 미검증

```python
broker = KISBroker(
    app_key=config.kis_app_key,      # 빈 문자열 "" 가능
    app_secret=config.kis_app_secret, # 빈 문자열 "" 가능
    ...
)
```

.env 미로딩(C4)과 결합하여 빈 시크릿으로 브로커 초기화. API 호출 시 인증 실패.

**수정**: 시크릿 필수 필드 검증 추가 (`assert config.kis_app_key, "KIS_APP_KEY required"`).

---

### M11. `strategy/base.py:36` — positions 타입 미지정

```python
class BaseStrategy:
    def __init__(self):
        self.positions = []  # List[???] — Position 타입 미정의
```

IDE 자동완성/타입체크 불가.

**수정**: `self.positions: List[Position] = []` + Position 타입 import.

---

### M12. `main.py:214` — backtest/engine.py 미존재

```python
from backtest.engine import BacktestEngine  # ❌ 파일 미존재
```

`backtest/historical_engine.py`는 존재하지만 `backtest/engine.py`는 없음.

**수정**: import 경로 수정 or `backtest/engine.py` → `backtest/historical_engine.py` 통일.

---

## MINOR (4건)

| # | 파일 | 이슈 |
|---|------|------|
| m1 | `sp500_futures.py` | `df.iloc[-5]` 등 인덱스 접근 시 `len(df) < 5` 범위 체크 누락 |
| m2 | `common/types.py` | `Signal.bb_upper` 등 선택적 필드 기본값 설계 불일치 |
| m3 | `sp500_futures.py:154` | `atr_breakout_mult` 기본값 0.5 근거 미문서화 |
| m4 | `sp500_futures.py` | `bars_held` 증가 로직이 `_check_exit`와 외부 호출에서 중복 가능 |

---

## 보안 리뷰

| 항목 | 상태 | 비고 |
|------|------|------|
| 하드코딩 시크릿 | ✅ 안전 | .env 패턴 사용 |
| .gitignore | ✅ 양호 | `.env`, `data_store/`, `*.db` 포함 |
| SQL Injection | ✅ 안전 | SQLAlchemy ORM 사용 |
| API 입력 검증 | ⚠️ 미흡 | ticker 포맷, 쿼리 파라미터 검증 없음 |
| CORS | ⚠️ 확인 필요 | `allow_origins=["*"]` 가능성 |
