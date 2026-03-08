# Phase 5: 배포 및 운영 가이드

| 항목 | 내용 |
|------|------|
| **문서 번호** | ATS-OPS-001 |
| **버전** | v1.0 |
| **최초 작성일** | 2026-02-25 |
| **최종 수정일** | 2026-02-25 |
| **상위 문서** | ATS-TST-001 테스트 명세서 v1.0 |
| **현재 Phase** | Phase 5 - Deployment & Operations |

---

## 변경 이력

| 버전 | 일자 | 변경 내용 | 작성자 |
|------|------|-----------|--------|
| v1.0 | 2026-02-25 | 초판 | SA/Ops |

---

## Part A: 배포 가이드

---

### 1. 사전 요구사항

#### 1.1 시스템 요구사항

| 항목 | 최소 사양 | 권장 사양 |
|------|-----------|-----------|
| OS | macOS 12+ / Ubuntu 22+ | macOS 14+ / Ubuntu 24+ |
| Python | 3.11 이상 | 3.12 |
| RAM | 2GB | 4GB |
| Disk | 500MB | 2GB |
| Network | 인터넷 접속 필수 | 유선 인터넷 |

#### 1.2 외부 계정 준비

| 서비스 | 준비 항목 | 가이드 |
|--------|-----------|--------|
| 한국투자증권 | ① 계좌 개설 ② 모의투자 신청 ③ API 발급 | [한투 OpenAPI](https://apiportal.koreainvestment.com/) |
| Telegram | ① Bot 생성 (@BotFather) ② Chat ID 확인 | [Telegram Bot API](https://core.telegram.org/bots) |

**한투 API 발급 절차:**

```
1. apiportal.koreainvestment.com 접속 → 회원가입
2. [API 신청] → 모의투자 APP KEY/SECRET 발급
3. [모의투자] → 가상 계좌번호 확인 + 가상자금 충전 (기본 1억)
4. APP KEY, APP SECRET, 계좌번호를 안전하게 저장
```

**Telegram Bot 설정:**

```
1. Telegram에서 @BotFather 대화 → /newbot → 봇 이름/아이디 설정
2. 발급받은 Bot Token 저장
3. 생성된 봇과 대화 시작 (메시지 1건 발송)
4. https://api.telegram.org/bot<TOKEN>/getUpdates 접속
5. result → message → chat → id 값이 Chat ID
```

---

### 2. 설치 (5분)

#### 2.1 원커맨드 설치

```bash
# 1. 프로젝트 클론 (또는 복사)
cd ~/projects
# git clone <repo-url> ats   # Git 사용 시
# 또는 파일을 ats/ 폴더로 복사

# 2. 자동 설정 (venv + 의존성 + DB 초기화 + 유니버스 로드)
cd ats
bash scripts/setup.sh
```

#### 2.2 수동 설치

```bash
cd ats

# 가상환경
python3 -m venv venv
source venv/bin/activate

# 의존성
pip install -r requirements.txt

# 환경 파일
cp .env.example .env
vi .env                    # API Key 등 입력

# DB 초기화
python main.py init-db

# 유니버스 로드
python scripts/load_universe.py
```

---

### 3. 환경 설정

#### 3.1 .env 파일 (필수)

```env
# ── 한국투자증권 API ──
KIS_APP_KEY=PSkq0...실제키...        # API Portal에서 발급
KIS_APP_SECRET=wNhR3...실제시크릿...  # API Portal에서 발급
KIS_ACCOUNT_NO=50123456-01           # 모의투자 계좌번호
KIS_IS_PAPER=true                    # ⚠️ 반드시 true로 시작

# ── Telegram ──
TELEGRAM_BOT_TOKEN=7012345678:AAF... # BotFather에서 발급
TELEGRAM_CHAT_ID=1234567890          # getUpdates에서 확인

# ── Database ──
DB_PATH=data_store/ats.db
```

> ⚠️ **보안 경고**: `.env` 파일은 절대 Git에 커밋하지 마세요. `.gitignore`에 이미 포함되어 있습니다.

#### 3.2 config.yaml 조정 (선택)

`config.yaml`은 기본값이 BRD v1.0 기준으로 설정되어 있습니다.
초기에는 변경 없이 사용하되, 필요 시 다음 항목을 조정합니다:

| 파라미터 | 기본값 | 조정 사유 |
|----------|--------|-----------|
| `strategy.ma_short` | 5 | 단기 이평선 기간 |
| `strategy.ma_long` | 20 | 장기 이평선 기간 |
| `exit.stop_loss_pct` | -0.03 | 손절 비율 (BR-S01: **변경 금지**) |
| `exit.take_profit_pct` | 0.07 | 익절 비율 |
| `portfolio.max_positions` | 10 | 최대 보유 종목 수 |
| `risk.max_order_amount` | 3000000 | 1회 최대 주문금액 |

> ⚠️ `exit.stop_loss_pct`는 BRD BR-S01에 의해 변경 불가입니다.

---

### 4. 배포 전 검증

#### 4.1 헬스체크 (필수)

```bash
source venv/bin/activate
python scripts/health_check.py
```

**예상 출력:**
```
============================================================
ATS Health Check
============================================================

[1] 설정 파일
  ✅ config.yaml + .env: config.yaml + .env 로드 완료 | mode=모의

[2] 데이터베이스
  ✅ SQLite DB: SQLite OK | 7개 테이블 | path=data_store/ats.db
  ✅ 유니버스 종목: 유니버스 30종목 로드 완료

[3] 한국투자증권 API
  ✅ 인증 토큰 발급: 토큰 발급 OK | 0.8초
  ✅ 시세 조회 (005930): 삼성전자 현재가=72,000원 | 0.3초
  ✅ 계좌 잔고 조회: 예수금=100,000,000원 | 평가금=0원 | 보유종목=0개

[4] Telegram 알림
  ✅ 메시지 발송: 메시지 발송 OK

============================================================
결과: ✅ 7 passed / ❌ 0 failed / 총 7건
============================================================

✅ 모든 점검 통과 — 시스템 기동 가능
```

#### 4.2 모의투자 연동 테스트 (필수)

```bash
# 장중(평일 09:00~15:30)에 실행
python scripts/paper_trade_test.py
```

**테스트 항목 (7건):**

| # | 항목 | API | 검증 내용 |
|---|------|-----|-----------|
| 1 | OAuth 토큰 발급 | POST /oauth2/tokenP | 토큰 발급 성공 |
| 2 | 현재가 조회 ×3 | GET /quotations/inquire-price | 삼성전자, SK하이닉스, NAVER |
| 3 | 일봉 OHLCV | GET /quotations/inquire-daily-price | 30행 이상 |
| 4 | 잔고 조회 | GET /trading/inquire-balance | 예수금 확인 |
| 5 | 매수 주문 | POST /trading/order-cash | 의도적 미체결 (5%↓ 지정가) |
| 6 | 체결 상태 | GET /trading/inquire-daily-ccld | SUBMITTED 확인 |
| 7 | 주문 취소 | POST /trading/order-rvsecncl | 취소 성공 |

> 장외 시간에는 주문 테스트(5~7)가 자동 스킵됩니다. 시세/잔고는 장외에도 조회 가능합니다.

---

### 5. 시스템 기동

#### 5.1 수동 기동

```bash
source venv/bin/activate
python main.py start
```

**기동 후 콘솔 출력:**
```
[09:00:01] [INFO    ] [state_manager     ] State transition | INIT → READY
[09:00:02] [INFO    ] [main_loop         ] Total capital: 100,000,000 won
[09:00:02] [INFO    ] [main_loop         ] System READY | capital=100,000,000 | positions=0
[09:30:00] [INFO    ] [scheduler         ] Trading session started
[09:30:00] [INFO    ] [state_manager     ] State transition | READY → RUNNING
[09:31:00] [INFO    ] [main_loop         ] Entry signals found: 2 stocks
...
```

#### 5.2 자동 기동 (crontab)

```bash
bash scripts/setup_cron.sh
```

설정 결과:
```
# ATS Auto-Trading (Mon-Fri 08:50 start)
50 8 * * 1-5 cd /home/user/ats && /home/user/ats/venv/bin/python3 main.py start >> data_store/logs/cron.log 2>&1
```

| 시간 | 이벤트 | 처리 |
|------|--------|------|
| 08:50 | crontab 기동 | INIT → READY |
| 09:30 | 매매 시작 | READY → RUNNING |
| 15:00 | 신규 매수 중단 | RUNNING → STOPPING |
| 15:30 | 장 마감 | 포지션 모니터링 종료 |
| 15:35 | 리포트 생성 | 일일 리포트 → STOPPED |

#### 5.3 수동 종료

```bash
# 프로세스 종료 (Ctrl+C 또는)
kill -SIGTERM $(pgrep -f "main.py start")
```

시스템은 SIGTERM/SIGINT 수신 시 안전하게 셧다운합니다:
미체결 주문 처리 → 최종 상태 저장 → Telegram 알림 → STOPPED

---

## Part B: 운영 가이드

---

### 6. 일상 운영

#### 6.1 일일 운영 체크리스트

| 시간 | 작업 | 방법 |
|------|------|------|
| 08:45 | 시스템 자동 기동 확인 | Telegram "✅ ATS 기동 완료" 메시지 확인 |
| 09:30 | 매매 시작 확인 | Telegram 매수 알림 모니터링 |
| 장중 | 비정상 알림 확인 | ⚠️/🚨 레벨 메시지 주시 |
| 15:35 | 일일 리포트 확인 | Telegram 📊 리포트 확인 |
| 16:00 | 로그 이상 확인 (선택) | `tail -100 data_store/logs/ats_*.log` |

#### 6.2 시스템 상태 확인

```bash
source venv/bin/activate
python main.py status
```

**출력 예시:**
```
==================================================
ATS Status
==================================================
  Config: MomentumSwing
  Mode:   모의투자
  Active positions: 3
  Pending orders:   0

  보유 종목:
    삼성전자     |   20주 |     72,000원 | +2.86%
    SK하이닉스   |   10주 |    135,000원 | +1.48%
    NAVER       |    5주 |    350,000원 | -0.57%

  최근 리포트 (2026-02-25):
    일일 수익률: +0.85%
    누적 수익률: +3.21%
    MDD: -1.50%
==================================================
```

#### 6.3 Telegram 알림 종류

| 알림 | 레벨 | 의미 | 조치 |
|------|------|------|------|
| ✅ ATS 기동 완료 | INFO | 정상 기동 | 확인만 |
| 📈 매수 주문 | INFO | 신규 매수 | 확인만 |
| ✅ 매수 체결 | INFO | 매수 완료 | 확인만 |
| 📉 🔴 손절 | WARNING | 손절 매도 | 확인만 (자동) |
| 📉 🟢 익절 | INFO | 익절 매도 | 확인만 |
| 📊 일일 리포트 | INFO | 장 마감 결산 | 수익률 확인 |
| ⚠️ 일일 손실 한도 | CRITICAL | 일일 -3% 도달 | 신규 매매 자동 중단 |
| 🚨 MDD 한도 | CRITICAL | MDD -10% 도달 | **시스템 자동 정지 — 즉시 확인** |
| 🚨 API 에러 | CRITICAL | API 연속 실패 | 네트워크/API Key 확인 |
| ⛔ ATS 중지 | INFO | 정상 종료 | 확인만 |

---

### 7. 모니터링

#### 7.1 로그 파일

```bash
# 오늘 로그 실시간
tail -f data_store/logs/ats_$(date +%Y-%m-%d).log

# 에러만 필터
grep "ERROR\|CRITICAL" data_store/logs/ats_$(date +%Y-%m-%d).log

# 매매 이벤트만
grep "Order\|Position\|signal\|STOP_LOSS\|TAKE_PROFIT" data_store/logs/ats_$(date +%Y-%m-%d).log
```

#### 7.2 모니터링 포인트 (SAD §16)

| ID | 조건 | 레벨 | 자동 조치 |
|----|------|------|-----------|
| M1 | API 연속 실패 5회 | WARNING | 로그 기록 |
| M2 | 시그널 스캔 60초 초과 | WARNING | 로그 기록 |
| M3 | 주문 지연 5초 초과 | WARNING | 로그 기록 |
| M4 | 일일 손실 -3% | CRITICAL | **신규 매매 중단** |
| M5 | MDD -10% | CRITICAL | **시스템 일시 정지** |
| M6 | 미체결 타임아웃 | INFO | 매수 취소 / 매도 시장가 전환 |
| M7 | ERROR 상태 진입 | CRITICAL | Telegram 알림 |

#### 7.3 DB 직접 조회

```bash
sqlite3 data_store/ats.db

-- 보유 포지션
SELECT position_id, stock_name, entry_price, quantity, pnl_pct, holding_days
FROM positions WHERE status = 'ACTIVE';

-- 당일 매매 이벤트
SELECT created_at, event_type, stock_code, detail
FROM trade_logs WHERE created_at LIKE '2026-02-25%'
ORDER BY created_at DESC LIMIT 20;

-- 일일 리포트 이력
SELECT trade_date, daily_return, cumulative_return, mdd, win_count, lose_count
FROM daily_reports ORDER BY trade_date DESC LIMIT 10;

-- 미체결 주문
SELECT order_id, stock_code, side, status, created_at
FROM orders WHERE status = 'SUBMITTED';

.quit
```

---

### 8. 장애 대응

#### 8.1 장애 유형별 대응

| 장애 | 증상 | 원인 | 조치 |
|------|------|------|------|
| **시스템 미기동** | Telegram 기동 메시지 없음 | crontab 미설정, 환경 에러 | `python main.py start` 수동 실행, 로그 확인 |
| **API 인증 실패** | "토큰 발급 실패" 로그 | APP KEY 만료, 네트워크 | .env 키 확인, 한투 API Portal 토큰 재발급 |
| **주문 거부** | "주문 거부" 알림 | 잔고 부족, 종목 거래정지 | 잔고 확인, 종목 상태 확인 |
| **손절 실패** | "STOP LOSS failed" 로그 | API 일시 장애 | 자동 시장가 재시도(NFR-A03), 수동 매도 필요 시 HTS 사용 |
| **시스템 ERROR** | 🚨 CRITICAL 알림 | 치명적 예외 | 로그 확인 → 원인 해소 → `python main.py start` 재기동 |
| **MDD 한도 도달** | 🚨 MDD -10% 알림 | 전략 연속 손실 | 시스템 자동 정지. 전략 점검 후 재기동 결정 |

#### 8.2 긴급 수동 매도

시스템 장애로 자동 매도가 불가할 경우:

```
1. 한투 HTS(eFriend Plus) 또는 MTS(한국투자) 앱에서 직접 매도
2. 매도 완료 후 DB 수동 업데이트:
   sqlite3 data_store/ats.db
   UPDATE positions SET status='CLOSED', exit_reason='MANUAL'
   WHERE stock_code='005930' AND status='ACTIVE';
3. 시스템 재기동
```

#### 8.3 데이터 복구

```bash
# DB 백업 (수동)
cp data_store/ats.db data_store/ats_backup_$(date +%Y%m%d).db

# DB 초기화 (모든 데이터 삭제 — 주의!)
rm data_store/ats.db
python main.py init-db
python scripts/load_universe.py
```

---

### 9. 설정 변경 가이드

#### 9.1 변경 가능 시간

| 시간대 | 변경 가능 여부 | 비고 |
|--------|----------------|------|
| 장 전 (~ 08:50) | ✅ 자유롭게 변경 | 시스템 미기동 상태 |
| 장중 (09:00~15:30) | ❌ **변경 금지** | 실행 중 설정 불일치 위험 |
| 장 후 (15:35 ~) | ✅ 자유롭게 변경 | 시스템 STOPPED 상태 |

#### 9.2 변경 절차

```bash
# 1. 시스템 중지 확인
python main.py status

# 2. config.yaml 수정
vi config.yaml

# 3. 변경 검증 (문법 확인)
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# 4. 다음 장에서 자동 반영
```

#### 9.3 변경 불가 항목

| 항목 | 값 | 사유 |
|------|-----|------|
| `exit.stop_loss_pct` | -0.03 | BR-S01: 손절 비율 불변 |
| `risk.daily_loss_limit` | -0.03 | BR-R01: PO 승인 없이 변경 불가 |
| `risk.mdd_limit` | -0.10 | BR-R02: PO 승인 없이 변경 불가 |

---

## Part C: 모의투자 → 실전 전환 가이드

---

### 10. 전환 체크리스트

#### 10.1 전환 전 필수 조건

| # | 조건 | 확인 |
|---|------|------|
| 1 | 모의투자 2주 이상 정상 운영 | ⬜ |
| 2 | 헬스체크 전항목 PASS | ⬜ |
| 3 | 일일 리포트 정상 수신 (14일+) | ⬜ |
| 4 | 손절/익절 자동 실행 확인 (각 1회 이상) | ⬜ |
| 5 | MDD 한도 미도달 (MDD > -10%) | ⬜ |
| 6 | API 에러 복구 확인 (1회 이상) | ⬜ |
| 7 | PO 실전 전환 승인 | ⬜ |

#### 10.2 전환 절차

```bash
# 1. 시스템 중지
python main.py start  # 장 후 자동 중지 대기

# 2. 실전 API Key 발급
#    한투 API Portal → [API 신청] → 실전투자 APP KEY/SECRET 발급

# 3. .env 변경
vi .env
# KIS_APP_KEY=실전_키
# KIS_APP_SECRET=실전_시크릿
# KIS_ACCOUNT_NO=실전_계좌번호
# KIS_IS_PAPER=false    ← ⚠️ 핵심 변경

# 4. DB 초기화 (모의투자 데이터 삭제)
cp data_store/ats.db data_store/ats_paper_backup.db
rm data_store/ats.db
python main.py init-db
python scripts/load_universe.py

# 5. 헬스체크
python scripts/health_check.py

# 6. 실전 첫 기동 (수동 — 모니터링 필수)
python main.py start
```

#### 10.3 실전 운영 시 주의사항

| 항목 | 모의투자 | 실전 |
|------|----------|------|
| 자금 | 가상 1억 | 실제 투자금 |
| 체결 | 즉시 체결 (대부분) | 호가/수량에 따라 미체결 가능 |
| 슬리피지 | 없음 | 시장가 주문 시 발생 |
| API 서버 | openapivts...29443 | openapi...9443 |
| 거래 수수료 | 없음 | 증권사 수수료 적용 |
| 세금 | 없음 | 증권거래세 0.18% |

> ⚠️ 실전에서는 **소규모 자금으로 1주 이상 안정성을 확인**한 후 본격 운영하세요.

---

## Part D: 파일 구조 최종 정리

---

### 11. 프로젝트 전체 파일 맵

```
ats/
├── main.py                          엔트리포인트 (CLI + DI)
├── config.yaml                      전략 설정 (Git 추적)
├── .env                             민감 정보 (Git 제외)
├── .env.example                     환경 변수 템플릿
├── .gitignore                       Git 제외 규칙
├── requirements.txt                 Python 의존성
├── run_tests.py                     독립 테스트 실행기
│
├── scripts/                         운영 스크립트
│   ├── setup.sh                     초기 설정 (원커맨드)
│   ├── setup_cron.sh                crontab 설정
│   ├── health_check.py              헬스체크 (7개 항목)
│   ├── paper_trade_test.py          모의투자 연동 테스트 (7단계)
│   └── load_universe.py             유니버스 로더 (샘플/CSV)
│
├── core/                            Orchestrator Layer
│   ├── state_manager.py             시스템 FSM (6개 상태)
│   ├── main_loop.py                 매매 메인 루프 (4-Phase)
│   └── scheduler.py                 장 시간 스케줄러
│
├── strategy/                        전략 플러그인
│   ├── base.py                      BaseStrategy 추상 클래스
│   └── momentum_swing.py            모멘텀 스윙 전략
│
├── risk/                            리스크 관리
│   └── risk_manager.py              RG1~RG4 게이트 + 한도
│
├── order/                           주문 실행
│   └── order_executor.py            매수/매도 + 재시도 + 미체결
│
├── position/                        포지션 관리
│   └── position_manager.py          상태 전이 + 트레일링
│
├── report/                          리포트 생성
│   └── report_generator.py          일일 리포트
│
├── data/                            Data Access Layer
│   ├── config_manager.py            YAML + .env 로드
│   └── market_data.py               시세 데이터 + 캐싱
│
├── infra/                           Infrastructure Layer
│   ├── logger.py                    로깅 설정
│   ├── broker/
│   │   ├── base.py                  BaseBroker 추상 클래스
│   │   └── kis_broker.py            한투 API 구현체
│   ├── db/
│   │   ├── models.py                SQLAlchemy ORM 7개 테이블
│   │   ├── connection.py            DB 연결 관리
│   │   └── repository.py            CRUD Repository
│   └── notifier/
│       ├── base.py                  BaseNotifier 추상 클래스
│       └── telegram_notifier.py     Telegram 구현체
│
├── common/                          공용 정의
│   ├── enums.py                     6개 Enum
│   ├── exceptions.py                10개 커스텀 예외
│   └── types.py                     12개 DataClass
│
├── tests/                           테스트 코드
│   ├── conftest.py                  공용 Fixture
│   ├── unit/                        단위 테스트 (7개 파일)
│   └── integration/                 통합 테스트 (1개 파일)
│
├── data_store/                      런타임 데이터 (Git 제외)
│   ├── ats.db                       SQLite DB
│   └── logs/                        일별 로그 파일
│       └── ats_YYYY-MM-DD.log
│
└── backtest/                        백테스트 (향후 구현)
    └── __init__.py
```

---

## Part E: 프로젝트 산출물 종합

---

### 12. 전체 산출물 일람

| Phase | 문서 번호 | 산출물 | 파일 |
|-------|-----------|--------|------|
| 0 | ATS-CHR-001 | 프로젝트 차터 v1.0 | Phase0_프로젝트차터_ATS_v1.0.md |
| 1 | ATS-BRD-001 | 비즈니스 요구사항 정의서 v1.0 | Phase1_BRD_ATS_v1.0.md |
| 1 | — | 유스케이스 명세 | Phase1_유스케이스_ATS_v1.0.md |
| 1 | — | 비기능 요구사항 | Phase1_비기능요구사항_ATS_v1.0.md |
| 2 | ATS-SAD-001 | 소프트웨어 아키텍처 설계서 v1.0 | Phase2_SAD_ATS_v1.0.md |
| 3 | ATS-IMP-001 | 구현 명세서 v1.0 | Phase3_IMP_ATS_v1.0.md |
| 3 | — | 소스 코드 (23개 모듈, 3,799 LOC) | ats/ 디렉토리 |
| 4 | ATS-TST-001 | 테스트 명세서 v1.0 | Phase4_TST_ATS_v1.0.md |
| 4 | — | 테스트 코드 (43건 PASS) | tests/ + run_tests.py |
| **5** | **ATS-OPS-001** | **배포 및 운영 가이드 v1.0** | **Phase5_OPS_ATS_v1.0.md** |
| 5 | — | 운영 스크립트 (5개) | scripts/ |

### 13. 정량 지표 종합

| 항목 | 수치 |
|------|------|
| 총 문서 | 10개 (Phase 0~5) |
| Python 소스 코드 | 23개 모듈, 3,799 LOC |
| 테스트 코드 | 43건 테스트, ~1,500 LOC |
| 운영 스크립트 | 5개 (setup, cron, health, paper_test, universe) |
| 설정 파일 | config.yaml + .env.example + requirements.txt |
| DB 테이블 | 7개 |
| BRD 업무 규칙 | 26개 (전항목 구현 완료) |
| 유스케이스 | 8개 (UC-01 ~ UC-08) |

---

## 14. 승인

### Phase 5 승인 체크리스트

| # | 항목 | 상태 |
|---|------|------|
| 1 | 설치 가이드 작성 (원커맨드 + 수동) | ✅ |
| 2 | 환경 설정 가이드 (.env + config.yaml) | ✅ |
| 3 | 헬스체크 스크립트 (7개 점검 항목) | ✅ |
| 4 | 모의투자 연동 테스트 스크립트 (7단계) | ✅ |
| 5 | 일상 운영 가이드 (체크리스트, 알림, 모니터링) | ✅ |
| 6 | 장애 대응 가이드 (6개 장애 유형) | ✅ |
| 7 | 모의투자 → 실전 전환 가이드 | ✅ |
| 8 | 프로젝트 산출물 종합 정리 | ✅ |
| 9 | PO 최종 승인 | ⬜ PO 리뷰 대기 |

### Phase Gate 5 (최종) 통과 조건

| 조건 | 충족 여부 |
|------|-----------|
| 배포/운영 가이드 문서 완성 | ✅ |
| 운영 스크립트 (헬스체크, 모의투자 테스트 등) 제공 | ✅ |
| 모의투자 → 실전 전환 절차 문서화 | ✅ |
| 전 Phase 산출물 완비 (Phase 0~5) | ✅ |
| PO 최종 승인 | ⬜ 대기 |

> **프로젝트 완료 조건**: PO 최종 승인 + 모의투자 2주 정상 운영 확인 후 실전 전환.

---

*본 문서는 ATS 프로젝트의 최종 산출물이며, Phase 0~4 전체 문서의 실행 가이드입니다.*
