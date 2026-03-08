# ATS — Automated Trading System

KOSPI200 / S&P500 / NASDAQ100 멀티마켓 자동매매 시스템과 실시간 트레이딩 대시보드.

모멘텀 스윙(6-Phase Pipeline)과 SMC(Smart Money Concepts, 4-Layer Scoring) 듀얼 전략 엔진을 기반으로, 시그널 탐지부터 주문 실행, 리스크 관리, 성과 분석까지 자동화된 매매 파이프라인을 제공한다.

---

## 주요 기능

- **듀얼 전략 엔진** — Momentum Swing (골든크로스/MACD/RSI) + SMC 4-Layer (BOS/CHoCH/OB/FVG) 스코어링
- **7-Layer MDD 방어** — 마켓 레짐, 트렌드 필터, 시그널 품질, 리스크 게이트, ATR 사이징, 5단계 청산, Progressive Trailing
- **실시간 시뮬레이션** — SSE(Server-Sent Events) 기반 실시간 매매 시뮬레이션
- **히스토리컬 백테스트** — 유니버스 단위 과거 데이터 백테스트 + 성과 지표 산출
- **웹 대시보드** — 9개 페이지 (차트 분석, 운영 모니터링, 리밸런싱, 리스크, 옵션 계산기 등)
- **브로커 연동** — 한국투자증권(KIS) REST API, 모의투자/실전투자 전환
- **알림** — Telegram Bot 실시간 매매 알림

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Python 3.11+, FastAPI, uvicorn, SQLAlchemy, SQLite |
| Frontend | React 19, TypeScript 5.9, Vite 7, lightweight-charts 4.1 |
| 데이터 | yfinance, pykrx, pandas, numpy |
| 브로커 | 한국투자증권 KIS REST API |
| 알림 | python-telegram-bot |
| 테스트 | pytest, 독립 단위 테스트 43건 |

---

## 시스템 아키텍처

### 3-Layer Monolith

```
┌─────────────────────────────────────────────────────┐
│  Orchestrator    core/main_loop, state_manager,     │
│                  scheduler                          │
├─────────────────────────────────────────────────────┤
│  Domain          strategy/  risk/  order/  position/ │
│                  simulation/  backtest/  analytics/  │
├─────────────────────────────────────────────────────┤
│  Infrastructure  infra/broker/  infra/db/            │
│                  infra/notifier/  infra/logger       │
└─────────────────────────────────────────────────────┘
        ↕ FastAPI REST + SSE ↕
┌─────────────────────────────────────────────────────┐
│  Frontend        React 19 + TypeScript + Vite       │
│                  lightweight-charts                  │
└─────────────────────────────────────────────────────┘
```

### Backend 모듈

| Layer | 모듈 | 역할 |
|-------|------|------|
| API | `api/app.py` | FastAPI + CORS + SSE lifespan |
| API | `api/routes.py` | `/analyze/{ticker}` 기술적 분석 |
| API | `api/sim_routes.py` | 실시간 시뮬레이션 |
| API | `api/rebalance_routes.py` | 포트폴리오 리밸런싱 |
| API | `api/backtest_routes.py` | 백테스트 실행/결과 |
| API | `api/market_overview.py` | 마켓 오버뷰 집계 |
| API | `api/ticker_list.py` | 티커 검색/해석 |
| Core | `core/main_loop.py` | 4-Phase 매매 루프 |
| Core | `core/state_manager.py` | FSM 상태관리 (INIT → READY → TRADING → STOPPED → ERROR) |
| Strategy | `strategy/momentum_swing.py` | 모멘텀 스윙 전략 |
| Strategy | `strategy/smc_strategy.py` | SMC 4-Layer 스코어링 전략 |
| Risk | `risk/risk_manager.py` | 리스크 게이트 (RG1-RG4) |
| Backtest | `backtest/historical_engine.py` | 히스토리컬 백테스터 |
| Backtest | `backtest/metrics.py` | 성과 지표 (Sharpe, MDD, Win Rate 등) |
| Simulation | `simulation/engine.py` | 실시간 시뮬레이션 엔진 |
| Infra | `infra/broker/kis_broker.py` | KIS API 브로커 |
| Infra | `infra/db/models.py` | ORM 모델 (7 테이블) |
| Infra | `infra/notifier/telegram_notifier.py` | Telegram 알림 |

### Frontend 페이지

| 경로 | 페이지 | 설명 |
|------|--------|------|
| `/` | Home | 랜딩 페이지 |
| `/dashboard` | Dashboard | 캔들스틱 차트, 기술적 지표, 드로잉 오버레이, 시그널 분석 |
| `/operations` | Operations | 포지션 테이블, 주문 로그, 시그널 리스트, 시스템 상태 |
| `/rebalance` | Rebalance | 백테스트 실행 (Momentum/SMC 선택), 성과 결과 표시 |
| `/risk` | Risk | 리스크 이벤트 로그, 게이트 상태 |
| `/performance` | Performance | 수익률 곡선, 트레이딩 저널 |
| `/scalp-analyzer` | ScalpAnalyzer | 스캘핑 분석 도구 |
| `/scalp-analyzer/fabio` | FabioStrategy | Fabio 스캘핑 전략 (AMT 3-Stage, Triple-A) |
| `/option-calculator` | OptionCalculator | Black-Scholes 옵션 가격 계산기 |

---

## 빠른 시작

### 사전 요구사항

- Python 3.11 이상
- Node.js 18 이상
- 한국투자증권 API 키 (모의투자 가능)

### 1. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 실제 값을 입력:

```env
# 한국투자증권 API
KIS_APP_KEY=your_app_key_here
KIS_APP_SECRET=your_app_secret_here
KIS_ACCOUNT_NO=12345678-01
KIS_IS_PAPER=true              # true: 모의투자, false: 실전투자

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Database
DB_PATH=data_store/ats.db
```

### 2. Backend 실행

```bash
# 가상환경 생성 및 활성화 (최초 1회)
python3 -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r ats/requirements.txt

# DB 초기화
python main.py init-db

# API 서버 실행
python main.py api
```

### 3. Frontend 실행

```bash
cd web/

# 패키지 설치 (최초 1회)
npm install

# 개발 서버 실행
npm run dev
```

브라우저에서 `http://localhost:5173` 접속.

---

## 전략 개요

### Strategy 1: Momentum Swing (6-Phase Pipeline)

| Phase | 이름 | 설명 |
|-------|------|------|
| 0 | Market Regime | MA200 Breadth로 BULL/NEUTRAL/BEAR 판단 |
| 1 | Trend Confirm | MA 정렬 + ADX 기반 추세 확인 (필터율 ~80.7%) |
| 2 | Trend Stage | BB squeeze + RSI + 52주 고점으로 EARLY/MID/LATE 판단 |
| 3 | Entry Signal | 골든크로스 + MACD 양전환 + RSI(52-78) + 거래량(1.5x) |
| 4 | Risk Gate | 일일 손실, MDD, 보유 한도, 현금 비율 체크 |
| 5 | Exit | 손절(-5%) > 익절(+20%) > 트레일링(ATR) > 데드크로스 > 보유기간(40일) |

### Strategy 2: SMC 4-Layer Scoring

| Layer | 비중 | 내용 |
|-------|------|------|
| 1. SMC Bias | 40점 | BOS/CHoCH 기반 시장 방향 판단 |
| 2. BB Squeeze + ATR | 20점 | 변동성 수축 → 확장 전환 포착 |
| 3a. OBV | 20점 | On-Balance Volume 추세 확인 |
| 3b. ADX + MACD | 20점 | 추세 강도 + 방향 일치 확인 |

진입 임계값: 총점 60/100 이상. 청산: ATR 손절/익절 + CHoCH 반전.

### 핵심 리스크 규칙

| ID | 규칙 | 값 | 설명 |
|----|------|------|------|
| BR-S01 | 개별 손절 | -10% | 절대 불변 |
| BR-R01 | 일일 손실 한도 | -5% | 도달 시 당일 매매 중단 |
| BR-R02 | MDD 한도 | -15% | 도달 시 시스템 정지 |
| BR-P01 | 최대 보유 종목 | 10 (BULL) | 레짐별 차등: 10/6/2 |
| BR-P02 | 종목당 최대 비중 | 15% (BULL) | 레짐별 차등: 15/12/5% |
| BR-P03 | 최소 현금 비율 | 30% | 항상 유지 |
| BR-P04 | 트레이드당 리스크 | 1.5% | ATR 기반 포지션 사이징 |

---

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/analyze/{ticker}` | 기술적 분석 (period, interval 파라미터) |
| POST | `/rebalance/backtest` | 백테스트 실행 (market, start_date, end_date, strategy) |
| GET | `/rebalance/backtest/status` | 백테스트 진행 상태 |
| GET | `/rebalance/backtest/result` | 캐시된 백테스트 결과 |
| GET | `/stream/{market_id}` | SSE 실시간 시뮬레이션 스트림 |

---

## 설정

### config.yaml

전략 파라미터를 코드가 아닌 설정 파일로 관리:

| 섹션 | 내용 |
|------|------|
| `system` | 시스템 이름, 버전, 로그 레벨 |
| `schedule` | 매매 시간대 (장전/장중/장후) |
| `universe` | 타겟 마켓 (KOSPI200), 제외 종목 |
| `strategy` | 이동평균, MACD, RSI, BB, 거래량 파라미터 |
| `smc_strategy` | SMC 4-Layer 가중치, ATR 배수, CHoCH 설정 |
| `exit` | 손절/익절/트레일링/보유기간 임계값 |
| `portfolio` | 최대 보유 종목, 비중 한도, 최소 현금 비율 |
| `risk` | 일일 손실 한도, MDD 한도, 1회 최대 주문금액 |
| `order` | 주문 유형, 타임아웃, 재시도 설정 |

### .env

시크릿 정보 관리. `.env.example`을 참조하여 `.env` 파일 생성.
절대 git에 커밋하지 않는다 (`.gitignore`에 포함).

---

## 테스트 및 개발

```bash
# 독립 단위 테스트 (43건)
python3 run_tests.py

# pytest 전체 (SQLAlchemy 필요)
pytest ats/tests/ -v

# TypeScript 타입 체크
cd web && npx tsc --noEmit

# 프로덕션 빌드
cd web && npm run build

# ESLint
cd web && npm run lint
```

---

## 스크립트

| 스크립트 | 설명 |
|---------|------|
| `ats/scripts/setup.sh` | 초기 환경 설정 |
| `ats/scripts/setup_cron.sh` | 크론잡 설정 |
| `ats/scripts/health_check.py` | 시스템 헬스체크 |
| `ats/scripts/paper_trade_test.py` | 모의투자 연동 테스트 |
| `ats/scripts/load_universe.py` | 유니버스 데이터 로드 |
| `ats/scripts/generate_backtest_data.py` | 백테스트 데이터 생성 |
| `ats/scripts/visualize_backtest.py` | 백테스트 결과 시각화 |

---

## 프로젝트 구조

```
atm-dev/
├── ats/                          # Backend (모든 Python 모듈)
│   ├── api/                      #   FastAPI 라우트
│   ├── analytics/                #   기술 지표 계산
│   ├── backtest/                 #   히스토리컬 백테스트
│   ├── common/                   #   공통 타입, Enum
│   ├── core/                     #   Orchestrator (메인 루프, FSM)
│   ├── data/                     #   설정 관리, 시장 데이터
│   ├── infra/                    #   브로커, DB, 알림
│   │   ├── broker/               #     KIS API
│   │   ├── db/                   #     SQLAlchemy ORM
│   │   └── notifier/             #     Telegram
│   ├── order/                    #   주문 실행
│   ├── position/                 #   포지션 관리
│   ├── report/                   #   리포트 생성
│   ├── risk/                     #   리스크 관리
│   ├── scripts/                  #   유틸리티 스크립트 (7개)
│   ├── simulation/               #   실시간 시뮬레이션
│   ├── strategy/                 #   전략 (Momentum, SMC)
│   ├── tests/                    #   pytest 테스트
│   └── requirements.txt          #   Python 의존성
├── web/                          # Frontend (React)
│   ├── src/
│   │   ├── components/           #   UI 컴포넌트
│   │   │   ├── dashboard/        #     차트, 분석, 시그널
│   │   │   ├── operations/       #     운영 모니터링
│   │   │   ├── rebalance/        #     백테스트 UI
│   │   │   └── layout/           #     네비게이션
│   │   ├── hooks/                #   커스텀 훅 (SSE, Polling)
│   │   ├── lib/                  #   유틸리티 (API, 차트, 엔진)
│   │   ├── pages/                #   페이지 컴포넌트 (9개)
│   │   └── App.tsx               #   라우터 설정
│   └── package.json              #   Node.js 의존성
├── stock_theory/                 # 트레이딩 이론 문서 (17개)
├── design_plan/                  # 설계 문서
├── FuturesScalpAnalyzer/         # 선물 스캘핑 분석 (JSX)
├── optionCalculator/             # 옵션 계산기 (HTML)
├── results/                      # 백테스트 결과
├── main.py                       # 엔트리포인트
├── run_tests.py                  # 독립 테스트 러너
├── config.yaml                   # 전략 설정 파일
├── .env.example                  # 환경변수 템플릿
├── CLAUDE.md                     # 개발자 상세 참조 문서
└── README.md                     # 프로젝트 소개
```

---

## 데이터베이스 스키마

SQLite + SQLAlchemy ORM. 7개 테이블:

| 테이블 | 설명 |
|--------|------|
| Universe | 종목 마스터 (코드, 이름, 마켓, 섹터) |
| Positions | 포지션 관리 (진입/청산 가격, 손절, 트레일링, PnL) |
| Orders | 주문 이력 (매수/매도, 상태, 체결 가격) |
| TradeLog | 이벤트 감사 추적 (JSON 상세) |
| DailyReport | 일간 성과 (PnL, MDD, 포지션 수) |
| ConfigHistory | 설정 변경 감사 |
| SystemLog | 시스템 로그 |

---

## 이론 문서

`stock_theory/` 디렉토리에 트레이딩 이론 및 전략 참조 문서 17개:

| 파일 | 내용 |
|------|------|
| `alphaStrategy.md` | Alpha 6-Phase 파이프라인 전체 스펙, 백테스트 결과 |
| `smcTheory.md` | SMC 이론 (BOS, CHoCH, Order Block, FVG) |
| `TradingLogicFlow.md` | Dow Theory, Wyckoff, Elliott Wave 이론-구현 매핑 |
| `ExitStrategyIndex.md` | 청산 전략 총람 (ATR/Structural/MA/SAR) |
| `mddDefenceStrategy.md` | MDD 방어 7-Layer 아키텍처 |
| `trendTheory.md` | 추세 판단 지표, 매크로 4필터 |
| `Kelly Criterion.md` | Kelly 공식 및 자산 배분 프레임워크 |
| `scalpingPlaybook.md` | Fabio 스캘핑 (AMT 3-Stage, Triple-A) |
| `futuresStrategy.md` | 확률 기반 선물 기술분석 (Z-Score, EV Engine) |
| `future_trading_stratedy.md` | ATR 기반 선물 매매 전략 |
| `kospi200_futures.md` | KOSPI200 선물 상품 규격 |
| `kospi200_options.md` | KOSPI200 옵션 상품 규격 |
| `kospi200_futures_simulation.md` | 선물 시뮬레이션 결과 |
| `kospi200_sim_report.md` | 옵션 전략 백테스트 리포트 |
| `optionCalculator.md` | 옵션 계산기 아키텍처 (Black-Scholes) |
| `BlackScholesEquation.md` | Black-Scholes 방정식 레퍼런스 |
| `TrendingJudgeIndex.md` | 추세 판단 인덱스 |

---

## 거래 비용

| 항목 | 값 |
|------|------|
| Slippage | 0.1% / side |
| Commission | 0.015% / side |
| 왕복 합계 | ~0.23% |

---

## 라이선스

Private repository. All rights reserved.
