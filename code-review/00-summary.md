# ATS 코드리뷰 종합 요약

> 리뷰 일자: 2026-03-14
> 대상: `ats/` (백엔드), `web/src/` (프론트엔드), `config.yaml`, `stock_theory/`

---

## 전체 스코어카드

| 영역 | 점수 | 비고 |
|------|------|------|
| 백엔드 코드 품질 | 7.0/10 | SP500 전략 견고, 나머지 전략 미구현 |
| 프론트엔드 코드 품질 | 8.5/10 | SSE/폴링 패턴 우수, 대형 파일 분리 필요 |
| TypeScript 타입 안전 | 8.0/10 | `any` 10건 존재 (TechnicalChart, api.ts) |
| Hook 품질 | 9.5/10 | AbortController/cleanup 완비 |
| 설정 관리 | 3.0/10 | YAML 9개 섹션 중 1개만 로딩 |
| 이론-구현 정합률 | 3.5/10 | 11개 이론 중 1개 완전 구현 |
| 테스트 커버리지 | 5.0/10 | 핵심 모듈 7개 커버, 17+ 미커버 |
| 보안 | 8.0/10 | 시크릿 관리 양호, API 입력 검증 부족 |
| **종합** | **B- (65/100)** | |

---

## 이슈 카운트

| 심각도 | 건수 | 즉시 조치 |
|--------|------|----------|
| CRITICAL | 4건 | main.py import 실패, config 로딩 결함, Division by Zero, .env 미로딩 |
| MAJOR | 12건 | NaN 전파, 매직넘버, 상태 소실, 파라미터 불일치 등 |
| MINOR | 10건 | 코드 스타일, 문서화, 경미한 중복 |

---

## 이론-구현 정합률 (전략별)

| 전략 | 이론 문서 | Config | 코드 | 정합률 |
|------|----------|--------|------|--------|
| S&P500 선물 (4-Layer) | ✅ | ✅ | ✅ | **90%** |
| 모멘텀 스윙 (6-Phase) | ✅ | ✅ | ⚠️ 기본만 | **25%** |
| SMC 4-Layer | ✅ | ✅ | ❌ | **10%** |
| Breakout-Retest | ✅ | ✅ | ❌ | **10%** |
| Mean Reversion | ❌ | ✅ | ❌ | **5%** |
| MDD 7-Layer 방어 | ✅ | ⚠️ | ⚠️ L1만 | **15%** |
| 스캘핑 (Fabio) | ✅ | ❌ | ❌ UI만 | **5%** |

---

## Top 5 즉시 조치 사항

| # | 액션 | 파일 | 영향 |
|---|------|------|------|
| 1 | `config_manager.py:load()` — 전체 YAML 섹션 로딩 구현 | `config_manager.py:226-239` | 설정 변경 무효 |
| 2 | `main.py` — 존재하지 않는 13개 모듈 import 정리 | `main.py:28-42` | 시스템 시작 불가 |
| 3 | 이론-설정 파라미터 정합성 (손절 -3% vs -5%, 리스크 1% vs 1.5%) | `config.yaml`, CLAUDE.md | 백테스트 왜곡 |
| 4 | `sp500_futures.py` — NaN/Division by Zero 방어 | `sp500_futures.py:707,742` | 런타임 크래시 |
| 5 | `analytics/indicators.py` 단위 테스트 추가 | 미존재 | 지표 계산 신뢰성 |

---

## 세부 문서

| 문서 | 내용 |
|------|------|
| [01-backend-review.md](./01-backend-review.md) | 백엔드 CRITICAL 4 + MAJOR 12 + MINOR 건 |
| [02-frontend-review.md](./02-frontend-review.md) | 프론트엔드 품질/타입/Hook 리뷰 |
| [03-theory-gap-analysis.md](./03-theory-gap-analysis.md) | 이론 11문서 vs 구현 정합률 |
| [04-config-audit.md](./04-config-audit.md) | config_manager 로딩 결함 + 수정 제안 |
| [05-test-coverage.md](./05-test-coverage.md) | 테스트 커버리지 현황 + 권장 추가 |
| [06-action-plan.md](./06-action-plan.md) | Tier 1~4 우선순위 액션 플랜 |
