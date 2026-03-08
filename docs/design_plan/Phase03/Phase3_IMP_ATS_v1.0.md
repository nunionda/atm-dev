# Phase 3: 구현 명세서 (Implementation Specification)

| 항목 | 내용 |
|------|------|
| **문서 번호** | ATS-IMP-001 |
| **버전** | v1.0 |
| **최초 작성일** | 2026-02-25 |
| **최종 수정일** | 2026-02-25 |
| **상위 문서** | ATS-SAD-001 소프트웨어 아키텍처 설계서 v1.0 |
| **현재 Phase** | Phase 3 - Implementation |

---

## 변경 이력

| 버전 | 일자 | 변경 내용 | 작성자 |
|------|------|-----------|--------|
| v1.0 | 2026-02-25 | 초판 - 전체 모듈 구현 완료 | SA |

---

## 1. 구현 요약

### 1.1 정량 지표

| 항목 | 수치 |
|------|------|
| Python 소스 파일 | 23개 (+ 13개 __init__.py) |
| 총 코드 라인(LOC) | 3,799줄 |
| 모듈 수 | 8개 패키지 |
| 설정 파일 | config.yaml, .env.example |
| 프로젝트 파일 | requirements.txt, .gitignore |

### 1.2 구현 순서 (Bottom-Up)

SAD §4.1에 따라 하위 레이어부터 구현하였다:

```
Layer 4: Infrastructure (infra/)     ← 먼저 구현
  ├── logger.py                       로깅 설정
  ├── broker/base.py + kis_broker.py  한투 API 어댑터
  ├── db/models.py + connection.py + repository.py  DB 레이어
  └── notifier/base.py + telegram_notifier.py       알림 어댑터

Layer 3: Data Access (data/)
  ├── config_manager.py               YAML+ENV 설정 로드
  └── market_data.py                  시세 데이터 제공

Layer 2: Domain (strategy/, risk/, order/, position/, report/)
  ├── strategy/base.py + momentum_swing.py   전략 엔진
  ├── risk/risk_manager.py                   리스크 관리
  ├── order/order_executor.py                주문 실행
  ├── position/position_manager.py           포지션 관리
  └── report/report_generator.py             리포트 생성

Layer 1: Orchestrator (core/)        ← 마지막 구현
  ├── state_manager.py                시스템 상태 FSM
  ├── main_loop.py                    매매 메인 루프
  └── scheduler.py                    장 시간 스케줄러

Entry Point:
  └── main.py                         DI 조립 + CLI
```

---

## 2. 모듈별 구현 상세

### 2.1 common/ — 공용 정의 (334 LOC)

| 파일 | LOC | 설명 | SAD 추적 |
|------|-----|------|----------|
| enums.py | 68 | 6개 Enum (SystemState, PositionStatus, OrderSide 등) | §12.2 |
| exceptions.py | 64 | 10개 커스텀 예외 (BrokerError, OrderError 등) | §5 |
| types.py | 202 | 12개 DataClass (Signal, ExitSignal, Portfolio 등) | §12.1 |

### 2.2 infra/ — 인프라 레이어 (1,100 LOC)

| 파일 | LOC | 설명 | SAD 추적 |
|------|-----|------|----------|
| logger.py | — | TimedRotatingFileHandler, 90일 보존 | §15 |
| broker/base.py | 68 | BaseBroker 추상 클래스 (8개 메서드) | §5.5 |
| broker/kis_broker.py | 462 | 한투 REST API 구현: 인증, 시세, 주문, 잔고 | §5.5, §11 |
| db/models.py | 159 | SQLAlchemy ORM 7개 테이블 | §10 |
| db/connection.py | — | SQLite 엔진/세션 관리 | §10 |
| db/repository.py | 280 | CRUD Repository (Position, Order, TradeLog 등) | §10 |
| notifier/base.py | — | BaseNotifier 추상 클래스 | §5.6 |
| notifier/telegram_notifier.py | 81 | Telegram Bot API 발송 + 리포트 포맷 | §13 |

**핵심 구현 포인트:**
- `KISBroker.RateLimiter`: 초당 5건 호출 제한 (NFR-P03)
- `KISBroker._ensure_token()`: 토큰 만료 1시간 전 자동 갱신 (SAD §11.3)
- `Repository`: Context Manager 기반 세션 관리 (`with self._session() as s:`)

### 2.3 data/ — 데이터 접근 레이어 (308 LOC)

| 파일 | LOC | 설명 | SAD 추적 |
|------|-----|------|----------|
| config_manager.py | 205 | 8개 Config DataClass + YAML/ENV 파싱 | §7 |
| market_data.py | 103 | 시세 조회 + OHLCV 캐싱 + 실시간 병합 | §5.7 |

**핵심 구현 포인트:**
- `ATSConfig`: 전략/청산/포트폴리오/리스크/주문 설정을 타입 안전하게 관리
- `MarketDataProvider.append_realtime_to_ohlcv()`: 캐시된 일봉에 실시간 데이터 반영

### 2.4 strategy/ — 전략 엔진 (323 LOC)

| 파일 | LOC | 설명 | SAD 추적 |
|------|-----|------|----------|
| base.py | — | BaseStrategy 추상 클래스 (3개 메서드) | §5.2 |
| momentum_swing.py | 323 | 모멘텀 스윙 전략 전체 구현 | §5.2, BRD §2 |

**핵심 구현 포인트:**
- `calculate_indicators()`: MA, MACD, RSI, BB, Volume MA를 pandas로 계산
- `scan_entry_signals()`: PS1(골든크로스) + PS2(MACD) → CF1(RSI) + CF2(거래량) → 강도 정렬
- `scan_exit_signals()`: ES1~ES5 우선순위 체크, 포지션당 1개 시그널만 반환

### 2.5 risk/ — 리스크 관리 (130 LOC)

| 파일 | LOC | 설명 | SAD 추적 |
|------|-----|------|----------|
| risk_manager.py | 130 | RG1~RG4 게이트 + BR-R01/R02 한도 + 매수수량 계산 | §5.3, BRD §3 |

**핵심 구현 포인트:**
- `check_risk_gates()`: 4단계 게이트 순차 체크, 첫 실패 시 즉시 반환
- `calculate_buy_quantity()`: 비중 한도, 현금 여유, 최대 주문금액 모두 반영

### 2.6 order/ — 주문 실행 (369 LOC)

| 파일 | LOC | 설명 | SAD 추적 |
|------|-----|------|----------|
| order_executor.py | 369 | 매수/매도 실행, 미체결 처리, 재시도 로직 | §5.4, BRD UC-03/04 |

**핵심 구현 포인트:**
- `execute_buy()`: 더블체크(BR-B02 물타기, BR-S04 재매수) → 주문 → DB → 알림
- `execute_sell()`: 손절 실패 시 시장가 무제한 재시도 (NFR-A03)
- `check_pending_orders()`: 매수 30분/매도 15분 타임아웃 자동 처리

### 2.7 position/ — 포지션 관리 (263 LOC)

| 파일 | LOC | 설명 | SAD 추적 |
|------|-----|------|----------|
| position_manager.py | 263 | PENDING→ACTIVE→CLOSING→CLOSED 상태 전이 | §9, BRD UC-03/04 |

**핵심 구현 포인트:**
- `activate_position()`: 체결 시 손절가/익절가/트레일링 자동 설정
- `update_trailing_high()`: 실시간 최고가 갱신 → 트레일링 스탑가 재계산

### 2.8 core/ — 오케스트레이터 (518 LOC)

| 파일 | LOC | 설명 | SAD 추적 |
|------|-----|------|----------|
| state_manager.py | 70 | FSM (6개 상태, 전이 규칙 강제) | §5.1 |
| main_loop.py | 320 | 4-Phase 매매 루프 + 초기화/마감/셧다운 | §5.7, §6 |
| scheduler.py | 128 | 장 시간 기반 상태 전이 + 메인 실행 루프 | §5.1 |

**핵심 구현 포인트:**
- `MainLoop.run_cycle()` 4-Phase:
  1. 포지션 모니터링 (청산 우선)
  2. 일일 손실 한도 체크
  3. 시그널 스캔 + 매수
  4. 미체결 주문 처리
- `Scheduler`: Ctrl+C 시그널 핸들링, 장 시간별 자동 상태 전이

---

## 3. 설정 파일

| 파일 | 용도 | 버전관리 |
|------|------|----------|
| config.yaml | 전략 파라미터 (BRD §2.5 전체 반영) | ✅ Git 추적 |
| .env.example | 민감 정보 템플릿 | ✅ Git 추적 |
| .env | 실제 API Key/Token | ❌ gitignore |
| .gitignore | Git 제외 규칙 | ✅ Git 추적 |
| requirements.txt | Python 의존성 11개 | ✅ Git 추적 |

---

## 4. BRD 업무 규칙 구현 매핑

### 4.1 매수 규칙 (BR-B)

| 규칙 | 구현 위치 | 구현 방식 |
|------|-----------|-----------|
| BR-B01 (주시그널+필터+게이트) | momentum_swing.py + risk_manager.py | scan_entry → check_risk_gates 파이프라인 |
| BR-B02 (물타기 금지) | order_executor.py L113 | `is_stock_held()` 체크 |
| BR-B03 (장초 30분 관망) | main_loop.py `_is_buy_allowed_time()` | buy_start="09:30" 설정 |
| BR-B04 (장마감 30분 전 매수 중단) | main_loop.py `_is_buy_allowed_time()` | buy_end="15:00" 설정 |
| BR-B05 (지정가 매수) | config.yaml `default_buy_type: LIMIT` | OrderExecutor에서 적용 |
| BR-B06 (미체결 30분 취소) | order_executor.py `check_pending_orders()` | buy_timeout_min=30 |

### 4.2 매도 규칙 (BR-S)

| 규칙 | 구현 위치 | 구현 방식 |
|------|-----------|-----------|
| BR-S01 (손절 무예외) | momentum_swing.py ES1 | 최우선 순위 체크, MARKET 주문 |
| BR-S02 (손절/익절 시장가) | momentum_swing.py | order_type="MARKET" 설정 |
| BR-S03 (청산 우선순위) | momentum_swing.py `scan_exit_signals()` | ES1→ES5 순차 체크, continue로 단일 반환 |
| BR-S04 (당일 재매수 금지) | order_executor.py L121 | `was_sold_today()` 체크 |
| BR-S05 (매도 미체결 시장가) | order_executor.py `check_pending_orders()` | sell_timeout_min=15 후 MARKET 재주문 |

### 4.3 리스크 규칙 (BR-R)

| 규칙 | 구현 위치 | 구현 방식 |
|------|-----------|-----------|
| BR-R01 (일일 손실 -3%) | risk_manager.py + main_loop.py Phase 2 | `check_daily_loss_limit()` → 매매 중단 |
| BR-R02 (MDD -10%) | risk_manager.py + main_loop.py | `check_mdd_limit()` → STOPPING 전이 |
| BR-R03 (리스크 게이트 필수) | main_loop.py Phase 3 | 매수 전 `check_risk_gates()` 필수 호출 |
| BR-R04 (1회 최대 금액) | risk_manager.py | `check_max_order_amount()` |

---

## 5. 승인

### Phase 3 승인 체크리스트

| # | 항목 | 상태 |
|---|------|------|
| 1 | SAD 디렉토리 구조대로 모듈이 생성되었다 | ✅ |
| 2 | 3-Layer 아키텍처 (Orchestrator→Domain→Infrastructure) 의존성 방향이 준수되었다 | ✅ |
| 3 | 추상 클래스 3개 (BaseStrategy, BaseBroker, BaseNotifier) 인터페이스가 구현되었다 | ✅ |
| 4 | BRD 업무 규칙 (BR-B/S/P/R/O) 전항목이 코드에 구현되었다 | ✅ |
| 5 | UC-01~UC-08 유스케이스가 코드에 반영되었다 | ✅ (UC-07 백테스트 stub) |
| 6 | ERD 7개 테이블 스키마가 SQLAlchemy 모델로 구현되었다 | ✅ |
| 7 | config.yaml이 BRD §2.5 전체 파라미터를 포함한다 | ✅ |
| 8 | .env 분리로 NFR-S01~S03 보안 요구사항이 준수되었다 | ✅ |
| 9 | 코드 리뷰 완료 | ⬜ PO 리뷰 대기 |

### Phase Gate 3 통과 조건

| 조건 | 충족 여부 |
|------|-----------|
| 전체 모듈 코드 작성 완료 | ✅ 3,799 LOC |
| SAD 추적 매트릭스 전항목 구현 확인 | ✅ |
| 설정 파일 작성 완료 | ✅ config.yaml + .env.example |
| PO 코드 리뷰 완료 | ⬜ PO 리뷰 대기 |

> **다음 단계**: PO 코드 리뷰 후 Phase 4(테스트) 진입.
> Phase 4에서는 단위 테스트, 통합 테스트, 모의투자 실행 테스트를 수행한다.

---

*본 문서는 SAD(ATS-SAD-001)의 하위 문서이며, 변경 시 버전을 갱신한다.*
