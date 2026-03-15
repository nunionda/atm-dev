# 우선순위 액션 플랜

> 리뷰 일자: 2026-03-14
> 관련 문서: 01~05 리뷰 결과 기반

---

## Tier 1: 즉시 (트레이딩/백테스트 전 필수)

| # | 액션 | 관련 이슈 | 파일 | 작업 규모 |
|---|------|----------|------|----------|
| A1 | **config_manager.py 전체 섹션 YAML 로딩** | C2, M8 | `config_manager.py:226-239` | 중 |
| A2 | **config_manager.py .env 로딩 구현** | C4, M10 | `config_manager.py:222-224` | 소 |
| A3 | **config_manager.py FileNotFoundError 로깅** | C3 | `config_manager.py:237-238` | 소 |
| A4 | **손절/리스크 파라미터 이론-설정 정합성** | D1, D2, D3 | `config.yaml` + CLAUDE.md 정리 | 소 |
| A5 | **sp500_futures.py NaN/Division by Zero 방어** | M3 | `sp500_futures.py:122-154` | 중 |

### A1 상세

`config_manager.py`의 `load()` 메서드를 확장하여 모든 YAML 섹션을 로딩.
→ `04-config-audit.md`의 수정 제안 코드 참조.

### A4 상세

CLAUDE.md에서 정의된 Business Rule과 config.yaml/코드 기본값의 불일치 해소:

| 파라미터 | CLAUDE.md | 결정 필요 |
|----------|----------|----------|
| BR-S01 손절 | -10% | -10% vs -5% vs -3% 중 확정 |
| BR-P04 리스크/트레이드 | 1.5% | 1% vs 1.5% 확정 |
| 최대보유일 | 레짐별 차등 | 고정 vs 동적 결정 |

---

## Tier 2: 높음 (백테스트 전)

| # | 액션 | 관련 이슈 | 파일 | 작업 규모 |
|---|------|----------|------|----------|
| B1 | **매직넘버 → SP500FuturesConfig 이동** | M4, M5, M6, M7 | `sp500_futures.py` 전체 | 대 |
| B2 | **FuturesPositionState 진입 시 초기화 수정** | M1 | `sp500_futures.py:50-57` | 소 |
| B3 | **config_manager.py 타입 검증 + 가중치 합계 체크** | M9 | `config_manager.py` | 중 |
| B4 | **config_manager.py 테스트 추가** | 05-test T1 | 신규 파일 | 중 |
| B5 | **analytics/indicators.py 단위 테스트** | 05-test T2 | 신규 파일 | 중 |
| B6 | **Progressive Trailing CLAUDE.md 사양 반영** | M7 | `sp500_futures.py:1027-1030` | 중 |

### B1 상세 (100+ 매직넘버 제거)

현재 `sp500_futures.py`의 4-Layer 스코어링에 하드코딩된 임계값들을 `SP500FuturesConfig`의 새 필드로 이동:

```python
# 현재 (하드코딩)
if abs_z >= 2.5: score += 25
elif abs_z >= 2.0: score += 20

# 수정 후 (config 기반)
if abs_z >= self.fc.zscore_tier1: score += self.fc.zscore_tier1_score
elif abs_z >= self.fc.zscore_tier2: score += self.fc.zscore_tier2_score
```

---

## Tier 3: 중간 (프로덕션 전)

| # | 액션 | 관련 이슈 | 작업 규모 |
|---|------|----------|----------|
| C1 | **main.py import 정리** (미존재 모듈 제거/stub) | C1, M12 | 소 |
| C2 | **FuturesPositionState DB 연동** | M2 | 대 |
| C3 | **Risk Gates RG1-RG4 독립 구현** | Gap L4 | 대 |
| C4 | **Progressive Trailing 4-tier 구현** | Gap L7 | 중 |
| C5 | **Market Regime (Phase 0) 구현** | Gap L1 | 대 |
| C6 | **프론트엔드 환경변수 URL** | F3 | 소 |
| C7 | **프론트엔드 대형 파일 분리** | F2 | 중 |
| C8 | **API 입력 검증 (Pydantic)** | 보안 | 중 |
| C9 | **run_tests.py → pytest 마이그레이션** | 05-test | 중 |

---

## Tier 4: 낮음 (향후 코드 품질)

| # | 액션 | 관련 이슈 |
|---|------|----------|
| D1 | SMC 전략: 구현 or Config/이론 문서 제거 결정 | Gap |
| D2 | Breakout-Retest: 구현 or 제거 결정 | Gap |
| D3 | Mean Reversion: Dataclass 정의 + 구현 결정 | Gap |
| D4 | Expected Value 엔진 구현 | Gap |
| D5 | 동적 Kelly Criterion 구현 | Gap |
| D6 | base.py 타입 힌트 강화 | M11 |
| D7 | 중복 UI 컴포넌트 추출 (Pill, Met, NIn) | F4 |
| D8 | SSE heartbeat 타임아웃 | F5 |

---

## 로드맵 요약

```
Week 1:  Tier 1 (A1-A5) — config 수정, NaN 방어
Week 2:  Tier 2 (B1-B6) — 매직넘버 제거, 테스트 추가
Week 3-4: Tier 3 (C1-C9) — 인프라, 리스크, FE 개선
Month 2+: Tier 4 (D1-D8) — 전략 결정, 코드 품질
```

---

## 의사결정 필요 사항

아래 항목은 기술적 판단이 아닌 비즈니스/전략적 결정 필요:

| # | 질문 | 선택지 |
|---|------|--------|
| Q1 | 손절 기준 확정 | -3% (선물) / -5% (주식) / -10% (CLAUDE.md) |
| Q2 | 리스크/트레이드 확정 | 1.0% vs 1.5% |
| Q3 | 미구현 전략 방향 | 구현 계획 수립 vs Config/이론 문서 정리 |
| Q4 | 테스트 프레임워크 | pytest 통일 vs run_tests.py 유지 |
| Q5 | 프로덕션 배포 목표 시점 | SP500만 우선 vs 전략 전체 |
