# 설정 감사 (Config Audit)

> 대상: `config.yaml` (346줄), `ats/data/config_manager.py` (239줄)
> 리뷰 일자: 2026-03-14

---

## 핵심 결함: YAML 로딩이 sp500_futures만 작동

### 현재 코드 (`config_manager.py:226-239`)

```python
def load(self) -> ATSConfig:
    config = ATSConfig()
    try:
        import yaml
        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}
        if "sp500_futures" in data:              # ← sp500_futures만 체크
            fc = data["sp500_futures"]
            for k, v in fc.items():
                if hasattr(config.sp500_futures, k):
                    setattr(config.sp500_futures, k, v)
    except FileNotFoundError:
        pass                                      # ← 무경고 무시
    return config
```

### 결과: 10개 섹션 중 1개만 로딩

| config.yaml 섹션 | Dataclass | YAML 로딩 | 실제 적용 |
|------------------|-----------|----------|----------|
| `sp500_futures` (35개 파라미터) | `SP500FuturesConfig` | ✅ | ✅ |
| `strategy` (10개) | `StrategyConfig` | ❌ | 기본값 |
| `exit` (4개) | `ExitConfig` | ❌ | 기본값 |
| `portfolio` (3개) | `PortfolioConfig` | ❌ | 기본값 |
| `risk` (3개) | `RiskConfig` | ❌ | 기본값 |
| `order` (5개) | `OrderConfig` | ❌ | 기본값 |
| `smc_strategy` (11개) | `SMCStrategyConfig` | ❌ | 기본값 |
| `breakout_retest` (28개) | `BreakoutRetestConfig` | ❌ | 기본값 |
| `mean_reversion` (14개) | ❌ Dataclass 미정의 | ❌ | 구현 없음 |
| `arbitrage` (33+개) | ❌ Dataclass 미정의 | ❌ | 구현 없음 |

---

## 추가 결함

### 1. `.env` 미로딩

```python
def __init__(self, config_path="config.yaml", env_path=".env"):
    self.env_path = env_path  # ← 저장만 하고 사용 안함
```

`ATSConfig`의 시크릿 필드(`kis_app_key`, `telegram_bot_token` 등)가 항상 빈 문자열.

### 2. FileNotFoundError 무시

```python
except FileNotFoundError:
    pass  # ← config.yaml 미존재 시 경고 없이 기본값
```

프로덕션에서 설정 파일 누락을 감지할 방법 없음.

### 3. 타입 검증 없음

```python
setattr(config.sp500_futures, k, v)  # v의 타입을 검증하지 않음
```

YAML에서 `"25"` (문자열)이 들어오면 `float` 필드에 `str` 할당. 런타임에 `TypeError` 발생 가능.

### 4. 가중치 합계 미검증

`weight_zscore + weight_trend + weight_momentum + weight_volume`의 합이 100인지 검증 없음.
사용자가 잘못된 가중치를 설정해도 무경고.

### 5. YAML 키 오타 무경고

```python
if hasattr(config.sp500_futures, k):
    setattr(...)
# else: 키가 Dataclass에 없으면 무시 — 오타 감지 불가
```

`config.yaml`에 `zscore_long_threshhold` (오타)를 쓰면 기본값 사용.

---

## 수정 제안

```python
import os
import yaml
from dotenv import load_dotenv

class ConfigManager:
    def __init__(self, config_path="config.yaml", env_path=".env"):
        self.config_path = config_path
        self.env_path = env_path

    def load(self) -> ATSConfig:
        config = ATSConfig()

        # 1. .env 로딩
        if os.path.exists(self.env_path):
            load_dotenv(self.env_path)
        config.kis_app_key = os.getenv("KIS_APP_KEY", "")
        config.kis_app_secret = os.getenv("KIS_APP_SECRET", "")
        config.kis_account_no = os.getenv("KIS_ACCOUNT_NO", "")
        config.kis_is_paper = os.getenv("KIS_IS_PAPER", "true").lower() == "true"
        config.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        config.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        config.db_path = os.getenv("DB_PATH", "data_store/ats.db")

        # 2. YAML 로딩
        try:
            with open(self.config_path) as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("config.yaml not found at %s, using defaults", self.config_path)
            return config

        # 3. 전체 섹션 로딩 (매핑)
        section_map = {
            "strategy": config.strategy,
            "exit": config.exit,
            "portfolio": config.portfolio,
            "risk": config.risk,
            "order": config.order,
            "smc_strategy": config.smc_strategy,
            "breakout_retest": config.breakout_retest,
            "sp500_futures": config.sp500_futures,
        }

        for section_name, section_obj in section_map.items():
            if section_name in data:
                self._apply_section(section_obj, data[section_name], section_name)

        # 4. system 레벨 설정
        if "system" in data:
            config.log_level = data["system"].get("log_level", config.log_level)

        return config

    def _apply_section(self, obj, values: dict, section_name: str):
        """섹션 값을 dataclass에 적용 + 타입 검증."""
        for k, v in values.items():
            if not hasattr(obj, k):
                logger.warning("[%s] Unknown config key: %s (ignored)", section_name, k)
                continue

            expected_type = type(getattr(obj, k))
            try:
                if expected_type == bool:
                    casted = bool(v)
                elif expected_type == int:
                    casted = int(v)
                elif expected_type == float:
                    casted = float(v)
                else:
                    casted = v
                setattr(obj, k, casted)
            except (ValueError, TypeError) as e:
                logger.error("[%s] Type error for %s: expected %s, got %s (%s)",
                            section_name, k, expected_type.__name__, type(v).__name__, e)
```

---

## config.yaml vs 코드 기본값 비교

주요 차이점 (config.yaml이 로딩되지 않아 기본값이 사용됨):

| 파라미터 | config.yaml | 코드 기본값 | 차이 |
|----------|-------------|------------|------|
| `portfolio.max_positions` | 60 | 10 | 6배 차이 |
| `portfolio.max_weight_per_stock` | 0.05 | 0.15 | 3배 차이 |
| `portfolio.min_cash_ratio` | 0.70 | 0.30 | 2.3배 차이 |
| `exit.stop_loss_pct` | -0.05 | -0.05 | 일치 (우연) |
| `exit.max_holding_days` | 40 | 40 | 일치 (우연) |
| `risk.daily_loss_limit` | -0.05 | -0.05 | 일치 (우연) |
| `risk.mdd_limit` | -0.15 | -0.15 | 일치 (우연) |

**결론**: 대부분의 전략 파라미터에서 config.yaml과 코드 기본값이 상이하며, YAML이 로딩되지 않아 의도하지 않은 기본값이 적용됨.
