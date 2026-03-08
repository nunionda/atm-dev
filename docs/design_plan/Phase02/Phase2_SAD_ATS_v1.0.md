# Phase 2: 소프트웨어 아키텍처 설계서 (SAD)

| 항목 | 내용 |
|------|------|
| **문서 번호** | ATS-SAD-001 |
| **버전** | v1.0 |
| **최초 작성일** | 2026-02-25 |
| **최종 수정일** | 2026-02-25 |
| **상위 문서** | ATS-BRD-001 비즈니스 요구사항 정의서 v1.0 |
| **현재 Phase** | Phase 2 - Analysis & Design |

---

## 변경 이력

| 버전 | 일자 | 변경 내용 | 작성자 |
|------|------|-----------|--------|
| v1.0 | 2026-02-25 | 초판 작성 | SA |

---

## 목차

**Part A: 소프트웨어 아키텍처 설계**
1. [아키텍처 개요](#1-아키텍처-개요)
2. [시스템 컨텍스트](#2-시스템-컨텍스트)
3. [기술 스택](#3-기술-스택)
4. [패키지 구조](#4-패키지-구조)
5. [컴포넌트 설계](#5-컴포넌트-설계)
6. [시퀀스 다이어그램](#6-시퀀스-다이어그램)
7. [설정 관리](#7-설정-관리)

**Part B: 데이터 모델 (ERD)**
8. [ERD 개요](#8-erd-개요)
9. [엔티티 정의](#9-엔티티-정의)
10. [테이블 스키마 상세](#10-테이블-스키마-상세)

**Part C: 인터페이스 설계**
11. [외부 API 인터페이스 (한투 API)](#11-외부-api-인터페이스)
12. [내부 모듈 인터페이스](#12-내부-모듈-인터페이스)
13. [알림 인터페이스 (Telegram)](#13-알림-인터페이스)

**Part D: 배포 및 운영**
14. [배포 아키텍처](#14-배포-아키텍처)
15. [로깅 및 모니터링](#15-로깅-및-모니터링)

**부록**
16. [BRD → SAD 추적 매트릭스](#16-추적-매트릭스)
17. [승인](#17-승인)

---

# Part A: 소프트웨어 아키텍처 설계

---

## 1. 아키텍처 개요

### 1.1 설계 원칙

| # | 원칙 | 근거 (BRD 추적) |
|---|------|-----------------|
| AP1 | **단일 프로세스 모놀리식** | 개인 투자용 시스템, 마이크로서비스 불필요. 복잡도 최소화 |
| AP2 | **계층형 아키텍처 (Layered)** | 관심사 분리: 전략 로직 ↔ 브로커 API ↔ 데이터 저장 |
| AP3 | **전략 플러그인 구조** | NFR-E01: 새로운 매매 전략 추가 용이 |
| AP4 | **브로커 어댑터 패턴** | NFR-E02: 증권사 변경 가능 |
| AP5 | **알림 어댑터 패턴** | NFR-E04: 알림 채널 추가 가능 |
| AP6 | **설정 외부화** | UC-06: YAML 파일로 전략 파라미터 관리 |
| AP7 | **장애 격리 (Fail-safe)** | BR-R01~R04: 리스크 규칙 위반 시 안전 방향으로 동작 |

### 1.2 아키텍처 스타일

```
┌─────────────────────────────────────────────────────────────────┐
│                      ATS (Automated Trading System)             │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Orchestrator Layer                       │  │
│  │  (Scheduler, MainLoop, SystemStateManager)                │  │
│  └──────────────────────┬────────────────────────────────────┘  │
│                         │                                       │
│  ┌──────────┬───────────┼───────────┬──────────────────────┐   │
│  │          │           │           │                      │   │
│  ▼          ▼           ▼           ▼                      ▼   │
│ ┌────┐  ┌──────┐  ┌─────────┐  ┌────────┐  ┌───────────┐     │
│ │Strat│  │Risk  │  │Order    │  │Position│  │Report     │     │
│ │egy  │  │Mgr   │  │Executor │  │Manager │  │Generator  │     │
│ │Engn │  │      │  │         │  │        │  │           │     │
│ └──┬─┘  └──┬───┘  └────┬────┘  └───┬────┘  └─────┬─────┘     │
│    │       │           │           │              │            │
│  ┌─┴───────┴───────────┴───────────┴──────────────┴────────┐   │
│  │                   Data Access Layer                       │  │
│  │  (MarketDataProvider, Repository, ConfigManager)          │  │
│  └──────────────────────┬────────────────────────────────────┘  │
│                         │                                       │
│  ┌──────────────────────┼────────────────────────────────────┐  │
│  │              Infrastructure Layer                          │  │
│  │                      │                                     │  │
│  │  ┌──────────┐  ┌────┴─────┐  ┌───────────┐  ┌─────────┐ │  │
│  │  │ Broker   │  │ Database │  │ Notifier  │  │ Logger  │ │  │
│  │  │ Adapter  │  │ (SQLite) │  │ Adapter   │  │         │ │  │
│  │  └────┬─────┘  └──────────┘  └─────┬─────┘  └─────────┘ │  │
│  └───────┼────────────────────────────┼──────────────────────┘  │
└──────────┼────────────────────────────┼──────────────────────────┘
           │                            │
           ▼                            ▼
    한국투자증권 API                 Telegram API
```

**3개 레이어 설명:**

| 레이어 | 역할 | 포함 컴포넌트 |
|--------|------|---------------|
| **Orchestrator** | 시스템 생명주기 관리, 매매 루프 조율 | Scheduler, MainLoop, SystemStateManager |
| **Domain** (중앙) | 비즈니스 로직 (전략, 리스크, 주문, 포지션, 리포트) | StrategyEngine, RiskManager, OrderExecutor, PositionManager, ReportGenerator |
| **Infrastructure** | 외부 시스템 연동, 영속화, 알림 | BrokerAdapter, Database, NotifierAdapter, Logger |

---

## 2. 시스템 컨텍스트

### 2.1 외부 시스템 연동

```
                    ┌──────────────┐
                    │   PO (투자자) │
                    └──────┬───────┘
                           │ config.yaml 편집
                           │ 수동 시작/중지 명령
                           │ 백테스트 실행
                           ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ 한국투자증권  │◄──►│              │───►│    Telegram     │
│   REST API   │    │    A T S     │    │    Bot API      │
│              │    │              │    │                 │
│ - 인증/토큰  │    │  Python 3.11 │    │ - 기동 알림     │
│ - 시세 조회  │    │  + SQLite    │    │ - 매매 알림     │
│ - 주문 전송  │    │              │    │ - 일일 리포트   │
│ - 체결 조회  │    │              │    │ - 긴급 알림     │
│ - 잔고 조회  │    │              │    │                 │
└─────────────┘    └──────┬───────┘    └─────────────────┘
                          │
                    ┌─────┴──────┐
                    │  cron / OS │
                    │ Scheduler  │
                    └────────────┘
                    (08:50 자동 기동)
```

### 2.2 외부 의존성

| 외부 시스템 | 프로토콜 | 인증 방식 | 주요 제약 |
|------------|----------|-----------|-----------|
| 한투 REST API | HTTPS (REST) | appkey + appsecret → OAuth 토큰 | 초당 5건 호출 제한, 토큰 24시간 만료 |
| 한투 WebSocket | WSS | 접속키 발급 | 실시간 체결가 스트리밍 (향후 확장) |
| Telegram Bot API | HTTPS (REST) | Bot Token | 초당 30건, 그룹 20건 제한 |
| KRX 유니버스 데이터 | 파일/웹 크롤링 | 없음 | KOSPI200 구성 변경 시 수동/반자동 업데이트 |

---

## 3. 기술 스택

### 3.1 핵심 기술

| 구분 | 기술 | 버전 | 선정 근거 |
|------|------|------|-----------|
| **언어** | Python | 3.11+ | 금융 데이터 라이브러리 풍부, PO 학습 용이 |
| **DB** | SQLite | 3.40+ | 단일 사용자, 서버 불필요, 파일 기반으로 백업 간편 |
| **HTTP** | requests / httpx | 최신 | 한투 REST API 호출 |
| **스케줄링** | APScheduler | 3.10+ | 시간 기반 매매 루프, 장 시작/마감 스케줄 |
| **기술적 분석** | pandas + ta-lib (or pandas_ta) | 최신 | 이평선, MACD, RSI, 볼린저밴드 계산 |
| **데이터 처리** | pandas | 2.0+ | DataFrame 기반 시세 데이터 처리 |
| **ORM** | SQLAlchemy (Core) | 2.0+ | 타입 안전한 DB 조작, 향후 DB 변경 대비 |
| **설정 관리** | PyYAML + python-dotenv | 최신 | config.yaml + .env 분리 |
| **알림** | python-telegram-bot | 최신 | Telegram 메시지 발송 |
| **로깅** | Python logging + loguru | 최신 | 구조화된 로깅, 파일 로테이션 |
| **테스트** | pytest + pytest-mock | 최신 | 단위/통합 테스트 |

### 3.2 디렉토리 구조

```
ats/
├── main.py                    # 엔트리포인트
├── config.yaml                # 전략 파라미터 설정
├── .env                       # API Key, Secret, Telegram Token (gitignore)
├── requirements.txt           # 의존성 목록
│
├── core/                      # Orchestrator Layer
│   ├── __init__.py
│   ├── scheduler.py           # 장 시간 기반 스케줄러
│   ├── main_loop.py           # 매매 메인 루프 (시그널스캔 + 모니터링)
│   └── state_manager.py       # 시스템 상태 관리 (INIT → READY → RUNNING → STOPPED)
│
├── strategy/                  # 전략 엔진 (플러그인 구조)
│   ├── __init__.py
│   ├── base.py                # Strategy 추상 클래스 (인터페이스)
│   ├── momentum_swing.py      # 모멘텀 스윙 전략 구현체
│   └── signal.py              # Signal 데이터 클래스 (시그널 결과 표현)
│
├── risk/                      # 리스크 관리
│   ├── __init__.py
│   └── risk_manager.py        # 리스크 게이트, 일일 손실 한도, MDD 감시
│
├── order/                     # 주문 실행
│   ├── __init__.py
│   └── order_executor.py      # 주문 생성, 전송, 체결 확인, 재시도
│
├── position/                  # 포지션 관리
│   ├── __init__.py
│   └── position_manager.py    # 포지션 CRUD, 상태 전이, PnL 계산
│
├── report/                    # 리포트 생성
│   ├── __init__.py
│   └── report_generator.py    # 일일/백테스트 리포트 생성
│
├── backtest/                  # 백테스트 모듈
│   ├── __init__.py
│   └── backtest_engine.py     # 과거 데이터로 전략 시뮬레이션
│
├── data/                      # Data Access Layer
│   ├── __init__.py
│   ├── market_data.py         # 시세 데이터 조회 및 가공
│   ├── universe.py            # KOSPI200 유니버스 관리
│   └── config_manager.py      # YAML 설정 로드, 변경 감지
│
├── infra/                     # Infrastructure Layer
│   ├── __init__.py
│   ├── broker/                # 브로커 어댑터
│   │   ├── __init__.py
│   │   ├── base.py            # Broker 추상 클래스 (인터페이스)
│   │   └── kis_broker.py      # 한국투자증권 API 구현체
│   ├── db/                    # 데이터베이스
│   │   ├── __init__.py
│   │   ├── models.py          # SQLAlchemy 모델 (테이블 정의)
│   │   ├── repository.py      # Repository 패턴 (CRUD 추상화)
│   │   └── connection.py      # DB 연결 관리
│   ├── notifier/              # 알림 어댑터
│   │   ├── __init__.py
│   │   ├── base.py            # Notifier 추상 클래스
│   │   └── telegram_notifier.py  # Telegram 구현체
│   └── logger.py              # 로깅 설정
│
├── common/                    # 공용 유틸리티
│   ├── __init__.py
│   ├── enums.py               # Enum 정의 (OrderSide, PositionStatus, ...)
│   ├── exceptions.py          # 커스텀 예외 클래스
│   └── types.py               # 공용 데이터 클래스 / TypedDict
│
├── tests/                     # 테스트
│   ├── unit/
│   ├── integration/
│   └── conftest.py
│
└── data_store/                # 런타임 데이터 (gitignore)
    ├── ats.db                 # SQLite DB 파일
    └── logs/                  # 로그 파일
        ├── ats_2026-02-25.log
        └── ...
```

---

## 4. 패키지 구조

### 4.1 의존성 방향 규칙

```
  Orchestrator (core/)
       │
       │ 의존
       ▼
  Domain (strategy/, risk/, order/, position/, report/)
       │
       │ 의존
       ▼
  Data Access (data/)
       │
       │ 의존
       ▼
  Infrastructure (infra/)
       │
       │ 호출
       ▼
  External Systems (한투 API, Telegram, SQLite)
```

**규칙:**
- 상위 레이어는 하위 레이어를 의존한다 (위 → 아래 방향만)
- 하위 레이어는 상위 레이어를 절대 import하지 않는다
- Domain 레이어는 Infrastructure의 추상 클래스(인터페이스)만 참조한다
- 구현체 주입은 `main.py`에서 Dependency Injection으로 수행한다

### 4.2 핵심 의존성 관계

```
main.py
  ├─ core/scheduler.py
  │    └─ core/main_loop.py
  │         ├─ strategy/momentum_swing.py  ← strategy/base.py 구현
  │         ├─ risk/risk_manager.py
  │         ├─ order/order_executor.py
  │         │    └─ infra/broker/kis_broker.py  ← infra/broker/base.py 구현
  │         ├─ position/position_manager.py
  │         │    └─ infra/db/repository.py
  │         └─ data/market_data.py
  │              └─ infra/broker/kis_broker.py
  ├─ report/report_generator.py
  │    └─ infra/notifier/telegram_notifier.py  ← infra/notifier/base.py 구현
  └─ data/config_manager.py
```

---

## 5. 컴포넌트 설계

### 5.1 SystemStateManager (시스템 상태 관리)

**상태 다이어그램:**

```
                  시스템 시작
                      │
                      ▼
                 ┌─────────┐
                 │  INIT   │  설정 로드, 토큰 발급, 데이터 초기화
                 └────┬────┘
                      │ 초기화 성공
                      ▼
                 ┌─────────┐
          ┌─────►│  READY  │  장 시작 대기 (09:00 이전)
          │      └────┬────┘
          │           │ 매매 활성 시간 진입 (09:30)
          │           ▼
          │      ┌──────────┐
          │      │ RUNNING  │  시그널 스캔 + 모니터링 루프 활성
          │      └────┬─────┘
          │           │
          │     ┌─────┼──────────────────┐
          │     │     │                  │
          │     ▼     ▼                  ▼
          │  장 마감  PO 수동 중지    리스크 한도 도달
          │     │     │                  │
          │     ▼     ▼                  ▼
          │  ┌──────────────────────────────┐
          │  │          STOPPING            │  미체결 주문 정리, 상태 저장
          │  └──────────────┬───────────────┘
          │                 │
          │                 ▼
          │  ┌──────────────────────────────┐
          └──│          STOPPED             │  매매 중단 (다음 장 READY 복귀)
             └──────────────────────────────┘

  ※ 어느 상태에서든 치명적 에러 발생 시 → ERROR 상태 전이
     ERROR 상태에서 복구 시도 → 성공 시 READY로 복귀
```

**상태 전이 테이블:**

| 현재 상태 | 이벤트 | 다음 상태 | 액션 |
|-----------|--------|-----------|------|
| INIT | 초기화 성공 | READY | 기동 알림 발송 |
| INIT | 초기화 실패 | ERROR | 긴급 알림 발송, 재시도 대기 |
| READY | 09:30 도달 | RUNNING | 매매 루프 시작 |
| RUNNING | 15:20 도달 | STOPPING | 신규 매수 중단 |
| RUNNING | PO 중지 명령 | STOPPING | 정리 작업 시작 |
| RUNNING | 일일 손실 -3% | STOPPING | 긴급 알림, 신규 매수 중단 |
| STOPPING | 정리 완료 | STOPPED | 일일 리포트 생성 |
| STOPPED | 다음 장 08:50 | INIT | 시스템 재기동 |
| ERROR | 복구 성공 | READY | 복구 알림 발송 |
| * | 치명적 에러 | ERROR | 긴급 알림, 포지션 보호 |

### 5.2 StrategyEngine (전략 엔진)

**Strategy 추상 클래스 (인터페이스):**

```python
# strategy/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List
import pandas as pd

@dataclass
class Signal:
    """시그널 결과를 표현하는 데이터 클래스"""
    stock_code: str          # 종목코드
    stock_name: str          # 종목명
    signal_type: str         # "BUY" | "SELL"
    primary_signals: List[str]     # 발생한 주 시그널 목록 ["PS1", "PS2"]
    confirmation_filters: List[str] # 통과한 보조 필터 ["CF1", "CF2"]
    strength: int            # 시그널 강도 (주시그널수 + 필터수)
    current_price: float     # 현재가
    timestamp: str           # 시그널 생성 시각

@dataclass
class ExitSignal:
    """청산 시그널 데이터 클래스"""
    stock_code: str
    stock_name: str
    exit_type: str           # "ES1"~"ES5"
    exit_reason: str         # "STOP_LOSS", "TAKE_PROFIT", ...
    order_type: str          # "MARKET" | "LIMIT"
    current_price: float
    pnl_pct: float           # 손익률
    timestamp: str

class BaseStrategy(ABC):
    """전략 추상 클래스 - NFR-E01 확장성을 위한 인터페이스"""
    
    @abstractmethod
    def scan_entry_signals(self, market_data: pd.DataFrame) -> List[Signal]:
        """매수 시그널을 스캔한다 (UC-02)"""
        pass
    
    @abstractmethod
    def scan_exit_signals(self, positions: List, market_data: pd.DataFrame) -> List[ExitSignal]:
        """청산 시그널을 스캔한다 (UC-04)"""
        pass
    
    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술적 지표를 계산하여 DataFrame에 추가한다"""
        pass
```

**MomentumSwingStrategy 구현체 핵심 로직:**

```python
# strategy/momentum_swing.py (핵심 로직 의사코드)

class MomentumSwingStrategy(BaseStrategy):
    
    def scan_entry_signals(self, market_data: pd.DataFrame) -> List[Signal]:
        signals = []
        for stock_code in self.universe:
            df = market_data[stock_code]
            df = self.calculate_indicators(df)
            
            # Step 1: 주 시그널 체크
            primary = []
            if self._check_golden_cross(df):    # PS1
                primary.append("PS1")
            if self._check_macd_buy(df):         # PS2
                primary.append("PS2")
            
            if not primary:
                continue  # 주 시그널 없으면 스킵
            
            # Step 2: 보조 필터 체크
            confirmations = []
            if self._check_rsi_range(df):        # CF1
                confirmations.append("CF1")
            if self._check_volume_surge(df):     # CF2
                confirmations.append("CF2")
            
            if not confirmations:
                continue  # 보조 필터 0개면 스킵
            
            # Step 3: 매수 후보 확정
            signals.append(Signal(
                stock_code=stock_code,
                primary_signals=primary,
                confirmation_filters=confirmations,
                strength=len(primary) + len(confirmations),
                ...
            ))
        
        # 시그널 강도 기준 내림차순 정렬
        return sorted(signals, key=lambda s: s.strength, reverse=True)
    
    def scan_exit_signals(self, positions, market_data) -> List[ExitSignal]:
        exit_signals = []
        for pos in positions:
            price = market_data[pos.stock_code].current_price
            
            # 우선순위대로 체크 (BRD 2.4절)
            if price <= pos.stop_loss_price:           # ES1: 손절
                exit_signals.append(ExitSignal(exit_type="ES1", order_type="MARKET", ...))
            elif price >= pos.take_profit_price:       # ES2: 익절
                exit_signals.append(ExitSignal(exit_type="ES2", order_type="MARKET", ...))
            elif price <= pos.trailing_stop_price:     # ES3: 트레일링
                exit_signals.append(ExitSignal(exit_type="ES3", order_type="MARKET", ...))
            elif self._check_dead_cross(pos, market_data):  # ES4
                exit_signals.append(ExitSignal(exit_type="ES4", order_type="LIMIT", ...))
            elif pos.holding_days > self.config.max_holding_days:  # ES5
                exit_signals.append(ExitSignal(exit_type="ES5", order_type="LIMIT", ...))
            else:
                # 트레일링 스탑 최고가 갱신
                pos.update_high_price(price)
        
        return exit_signals
```

### 5.3 RiskManager (리스크 관리)

```python
# risk/risk_manager.py (인터페이스 및 핵심 로직)

class RiskManager:
    """
    BRD 3.3~3.4절의 리스크 규칙을 구현한다.
    모든 매수 주문 전에 반드시 check_risk_gates()를 호출해야 한다.
    """
    
    def check_risk_gates(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """
        리스크 게이트 RG1~RG4를 순차적으로 체크한다.
        하나라도 실패하면 매수를 거부한다.
        
        Returns:
            RiskCheckResult(passed=True/False, failed_gate="RG2", reason="...")
        """
        # RG1: 포트폴리오 여유 체크
        if portfolio.active_count >= self.config.max_positions:
            return RiskCheckResult(passed=False, failed_gate="RG1",
                reason=f"보유종목 {portfolio.active_count}/{self.config.max_positions} 초과")
        
        # RG2: 종목 비중 한도 체크
        buy_amount = portfolio.total_capital * self.config.max_weight_per_stock
        if buy_amount / portfolio.total_capital > self.config.max_weight_per_stock:
            return RiskCheckResult(passed=False, failed_gate="RG2", ...)
        
        # RG3: 일일 매매금액 한도 체크
        if portfolio.daily_buy_amount + buy_amount > self.config.daily_buy_limit:
            return RiskCheckResult(passed=False, failed_gate="RG3", ...)
        
        # RG4: 볼린저밴드 상단 체크
        if signal.current_price >= signal.bb_upper:
            return RiskCheckResult(passed=False, failed_gate="RG4", ...)
        
        return RiskCheckResult(passed=True)
    
    def check_daily_loss_limit(self, portfolio: Portfolio) -> bool:
        """BR-R01: 일일 총 손실 -3% 체크. True이면 매매 중단."""
        daily_pnl_pct = portfolio.daily_pnl / portfolio.total_capital
        return daily_pnl_pct <= self.config.daily_loss_limit  # -0.03
    
    def check_mdd_limit(self, portfolio: Portfolio) -> bool:
        """BR-R02: MDD -10% 체크. True이면 시스템 일시 정지."""
        return portfolio.mdd <= self.config.mdd_limit  # -0.10
```

### 5.4 OrderExecutor (주문 실행기)

```python
# order/order_executor.py (인터페이스)

class OrderExecutor:
    """
    UC-03, UC-04의 주문 실행 로직.
    BrokerAdapter를 통해 실제 주문을 전송한다.
    """
    
    def __init__(self, broker: BaseBroker, notifier: BaseNotifier):
        self.broker = broker      # 브로커 어댑터 (DI)
        self.notifier = notifier  # 알림 어댑터 (DI)
    
    def execute_buy(self, signal: Signal, portfolio: Portfolio) -> OrderResult:
        """
        매수 주문 실행 (UC-03 기본 흐름)
        
        1. 매수 수량 계산 (BRD 2.7절)
        2. 더블체크 (BR-B02, BR-S04)
        3. 주문 전송 (재시도 3회)
        4. 포지션 기록 (PENDING)
        5. 알림 발송
        """
        pass
    
    def execute_sell(self, exit_signal: ExitSignal, position: Position) -> OrderResult:
        """
        매도 주문 실행 (UC-04 기본 흐름)
        
        1. 주문 유형 결정 (시장가/지정가)
        2. 주문 전송
        3. 포지션 상태 → CLOSING
        4. 알림 발송
        """
        pass
    
    def check_pending_orders(self):
        """
        미체결 주문 처리
        - 매수: 30분 초과 시 취소 (BR-B06)
        - 매도: 15분 초과 시 시장가 재주문 (BR-S05)
        """
        pass
```

### 5.5 BrokerAdapter (브로커 어댑터)

```python
# infra/broker/base.py

class BaseBroker(ABC):
    """브로커 추상 클래스 - NFR-E02 증권사 교체 대비"""
    
    @abstractmethod
    def authenticate(self) -> str:
        """인증 토큰 발급"""
        pass
    
    @abstractmethod
    def get_price(self, stock_code: str) -> PriceData:
        """현재가 조회"""
        pass
    
    @abstractmethod
    def get_ohlcv(self, stock_code: str, period: int) -> pd.DataFrame:
        """일봉 OHLCV 데이터 조회"""
        pass
    
    @abstractmethod
    def place_order(self, order: Order) -> OrderResponse:
        """주문 전송"""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """주문 취소"""
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderStatus:
        """주문 체결 상태 조회"""
        pass
    
    @abstractmethod
    def get_balance(self) -> Balance:
        """계좌 잔고 조회"""
        pass
```

```python
# infra/broker/kis_broker.py

class KISBroker(BaseBroker):
    """
    한국투자증권 API 구현체.
    
    API Rate Limit: 초당 5건 (NFR-P03)
    토큰 만료: 24시간 (자동 갱신 필요)
    """
    BASE_URL = "https://openapi.koreainvestment.com:9443"
    
    def __init__(self, app_key: str, app_secret: str, account_no: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.token: Optional[str] = None
        self.token_expires: Optional[datetime] = None
        self._rate_limiter = RateLimiter(max_calls=5, period=1.0)
    
    # ... 각 메서드 한투 API 엔드포인트 매핑 구현
```

### 5.6 NotifierAdapter (알림 어댑터)

```python
# infra/notifier/base.py

class BaseNotifier(ABC):
    """알림 추상 클래스 - NFR-E04 채널 추가 대비"""
    
    @abstractmethod
    def send_message(self, message: str, level: str = "INFO") -> bool:
        """메시지 발송. level: INFO, WARNING, CRITICAL"""
        pass
    
    @abstractmethod
    def send_report(self, report: DailyReport) -> bool:
        """일일 리포트 발송"""
        pass
```

### 5.7 MainLoop (매매 메인 루프)

```python
# core/main_loop.py (핵심 루프 의사코드)

class MainLoop:
    """
    장중 매매의 핵심 루프.
    1분 간격으로 시그널 스캔 + 포지션 모니터링을 실행한다.
    """
    
    def run_cycle(self):
        """매매 주기 1회 실행 (1분마다 호출)"""
        
        # Phase 1: 포지션 모니터링 (UC-04) — 청산이 진입보다 우선
        if self.position_manager.has_active_positions():
            market_data = self.data_provider.get_current_prices(
                self.position_manager.get_active_codes()
            )
            exit_signals = self.strategy.scan_exit_signals(
                self.position_manager.get_active_positions(), market_data
            )
            for es in exit_signals:
                self.order_executor.execute_sell(es, ...)
        
        # Phase 2: 일일 손실 한도 체크 (BR-R01)
        if self.risk_manager.check_daily_loss_limit(self.portfolio):
            self.state_manager.transition_to(SystemState.STOPPING)
            return
        
        # Phase 3: 시그널 스캔 (UC-02) — 매매 활성 시간에만
        if self._is_buy_allowed_time():
            market_data = self.data_provider.get_universe_data()
            signals = self.strategy.scan_entry_signals(market_data)
            
            for signal in signals:
                risk_result = self.risk_manager.check_risk_gates(signal, self.portfolio)
                if risk_result.passed:
                    self.order_executor.execute_buy(signal, self.portfolio)
        
        # Phase 4: 미체결 주문 처리
        self.order_executor.check_pending_orders()
    
    def _is_buy_allowed_time(self) -> bool:
        """BR-B03, BR-B04: 매수 허용 시간대 확인 (09:30~15:00)"""
        now = datetime.now().time()
        return time(9, 30) <= now <= time(15, 0)
```

---

## 6. 시퀀스 다이어그램

### 6.1 UC-01: 시스템 기동 시퀀스

```
Scheduler     MainLoop    ConfigMgr    KISBroker    PositionMgr   MarketData    Telegram
    │              │           │            │             │            │            │
    │──(08:50)────►│           │            │             │            │            │
    │  기동 명령    │           │            │             │            │            │
    │              │──load()──►│            │             │            │            │
    │              │◄──config──│            │             │            │            │
    │              │           │            │             │            │            │
    │              │──authenticate()──────►│             │            │            │
    │              │◄──token───────────────│             │            │            │
    │              │           │            │             │            │            │
    │              │──load_positions()────────────────►│            │            │
    │              │◄──positions─────────────────────── │            │            │
    │              │           │            │             │            │            │
    │              │──update_universe()─────────────────────────►│            │
    │              │──update_ohlcv()────────────────────────────►│            │
    │              │◄──OK──────────────────────────────────────── │            │
    │              │           │            │             │            │            │
    │              │  state = READY         │             │            │            │
    │              │           │            │             │            │            │
    │              │──send("기동 완료")──────────────────────────────────────────►│
    │              │◄──OK──────────────────────────────────────────────────────── │
    │              │           │            │             │            │            │
```

### 6.2 UC-02+03: 시그널 스캔 → 매수 주문 시퀀스

```
MainLoop     Strategy    MarketData   KISBroker    RiskMgr    OrderExec   PositionMgr  Telegram
    │            │           │           │           │           │            │           │
    │──scan()──►│           │           │           │           │            │           │
    │           │──get()───►│           │           │           │            │           │
    │           │           │──prices()──►│          │           │            │           │
    │           │           │◄──data──── │          │           │            │           │
    │           │◄──df─────│           │           │           │            │           │
    │           │           │           │           │           │            │           │
    │           │ calculate_indicators()│           │           │            │           │
    │           │ check PS1,PS2         │           │           │            │           │
    │           │ check CF1,CF2         │           │           │            │           │
    │           │           │           │           │           │            │           │
    │◄─signals──│           │           │           │           │            │           │
    │           │           │           │           │           │            │           │
    │ [for each signal]     │           │           │           │            │           │
    │──check_risk_gates()──────────────────────────►│           │            │           │
    │◄──passed──────────────────────────────────────│           │            │           │
    │           │           │           │           │           │            │           │
    │──execute_buy()───────────────────────────────────────────►│            │           │
    │           │           │           │           │           │            │           │
    │           │           │           │──place()──►│          │            │           │
    │           │           │           │◄──ok──────│          │            │           │
    │           │           │           │           │           │            │           │
    │           │           │           │           │──save(PENDING)────────►│           │
    │           │           │           │           │◄──ok─────────────────── │           │
    │           │           │           │           │           │            │           │
    │           │           │           │           │──notify()─────────────────────────►│
    │◄──result──────────────────────────────────────────────────│            │           │
    │           │           │           │           │           │            │           │
```

### 6.3 UC-04: 포지션 모니터링 → 청산 시퀀스

```
MainLoop     Strategy    PositionMgr   MarketData   OrderExec   KISBroker    Telegram
    │            │           │            │            │            │           │
    │──get_active()────────►│            │            │            │           │
    │◄──positions───────────│            │            │            │           │
    │            │           │            │            │            │           │
    │──scan_exit()────────►│            │            │            │           │
    │           │──get_prices()─────────►│            │            │           │
    │           │           │◄──prices────│            │            │           │
    │           │           │            │            │            │           │
    │           │ [우선순위별 체크]        │            │            │           │
    │           │ ES1(손절) → ES2(익절) → ES3(트레일링) → ES4 → ES5           │
    │           │           │            │            │            │           │
    │◄─exit_signals─────── │            │            │            │           │
    │            │           │            │            │            │           │
    │ [for each exit_signal] │            │            │            │           │
    │──execute_sell()──────────────────────────────►│            │           │
    │            │           │            │           │──place()──►│           │
    │            │           │            │           │◄──ok───── │           │
    │            │           │            │           │            │           │
    │            │──update(CLOSING)──────►│           │            │           │
    │            │           │            │           │──notify()────────────►│
    │            │           │            │           │            │           │
    │ [체결 확인 후]         │            │           │            │           │
    │            │──update(CLOSED)───────►│           │            │           │
    │            │──save_pnl()───────────►│           │            │           │
    │            │           │            │            │            │           │
```

---

## 7. 설정 관리

### 7.1 설정 파일 구조

**config.yaml** (전략 파라미터 — 버전 관리 대상):

```yaml
# ===== ATS 전략 설정 파일 =====
# 문서 참조: ATS-BRD-001 v1.0, Section 2.5

system:
  name: "ATS-MomentumSwing"
  version: "1.0.0"
  log_level: "INFO"

schedule:
  pre_market_start: "08:50"     # 시스템 기동
  market_open: "09:00"          # 장 시작
  buy_start: "09:30"            # 매수 시작 (관망 후)
  buy_end: "15:00"              # 신규 매수 중단
  market_close: "15:30"         # 장 마감
  report_time: "15:35"          # 일일 리포트 생성
  scan_interval_sec: 60         # 스캔 주기 (초)

universe:
  type: "KOSPI200"
  exclude: []                   # 제외 종목 코드 리스트

strategy:
  name: "MomentumSwing"
  
  # 이동평균선
  ma_short: 5
  ma_long: 20
  
  # MACD
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  
  # RSI
  rsi_period: 14
  rsi_lower: 30
  rsi_upper: 70
  
  # 볼린저밴드
  bb_period: 20
  bb_std: 2
  
  # 거래량
  volume_ma_period: 20
  volume_multiplier: 1.5

exit:
  stop_loss_pct: -0.03          # 손절 -3%
  take_profit_pct: 0.07         # 익절 +7%
  trailing_stop_pct: -0.03      # 트레일링 스탑 -3%
  max_holding_days: 10          # 최대 보유일

portfolio:
  max_positions: 10             # 최대 보유 종목수
  max_weight_per_stock: 0.15    # 종목당 최대 비중 15%
  min_cash_ratio: 0.20          # 최소 현금 비율 20%
  
risk:
  daily_loss_limit: -0.03       # 일일 손실 한도 -3%
  mdd_limit: -0.10              # MDD 한도 -10%
  max_order_amount: 3000000     # 1회 최대 주문금액

order:
  default_buy_type: "LIMIT"     # 매수: 지정가
  buy_timeout_min: 30           # 매수 미체결 취소 시간(분)
  sell_timeout_min: 15          # 매도 미체결 → 시장가 전환 시간(분)
  max_retry: 3                  # 주문 재시도 횟수
  retry_interval_sec: 5         # 재시도 간격(초)
```

**.env** (민감 정보 — gitignore 대상):

```env
# 한국투자증권 API
KIS_APP_KEY=your_app_key_here
KIS_APP_SECRET=your_app_secret_here
KIS_ACCOUNT_NO=12345678-01
KIS_IS_PAPER=true              # true: 모의투자, false: 실전

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Database
DB_PATH=./data_store/ats.db
```

---

# Part B: 데이터 모델 (ERD)

---

## 8. ERD 개요

### 8.1 엔티티 관계도

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│   Universe   │       │    Position      │       │    Order     │
│──────────────│       │──────────────────│       │──────────────│
│ PK stock_code│◄──────│ FK stock_code    │──────►│ FK position_id│
│    name      │       │ PK position_id   │       │ PK order_id  │
│    market    │       │    status        │       │    side      │
│    sector    │       │    entry_price   │       │    order_type│
│    is_active │       │    quantity      │       │    status    │
│    updated_at│       │    stop_loss     │       │    price     │
└──────────────┘       │    take_profit   │       │    quantity  │
                       │    trailing_high │       │    filled_qty│
                       │    entry_date    │       │    broker_id │
                       │    exit_date     │       │    created_at│
                       │    exit_price    │       │    filled_at │
                       │    pnl          │       └──────────────┘
                       │    pnl_pct      │
                       │    exit_reason  │
                       └──────────────────┘
                                │
                                │ 1:N
                                ▼
                       ┌──────────────────┐
                       │   TradeLog       │
                       │──────────────────│
                       │ PK log_id        │
                       │ FK position_id   │
                       │    event_type    │
                       │    detail        │
                       │    created_at    │
                       └──────────────────┘

┌──────────────────┐       ┌──────────────────┐
│  DailyReport     │       │  SystemLog       │
│──────────────────│       │──────────────────│
│ PK report_id     │       │ PK log_id        │
│    trade_date    │       │    level         │
│    total_buy     │       │    module        │
│    total_sell    │       │    message       │
│    realized_pnl  │       │    created_at    │
│    unrealized_pnl│       └──────────────────┘
│    daily_return  │
│    cumul_return  │
│    mdd           │
│    win_count     │
│    lose_count    │
│    cash_balance  │
│    total_value   │
│    created_at    │
└──────────────────┘

┌──────────────────┐
│  ConfigHistory   │
│──────────────────│
│ PK history_id    │
│    param_key     │
│    old_value     │
│    new_value     │
│    changed_at    │
└──────────────────┘
```

### 8.2 엔티티 요약

| 엔티티 | 설명 | BRD 추적 |
|--------|------|----------|
| **Universe** | KOSPI200 유니버스 종목 마스터 | BRD 2.1 매매 대상 |
| **Position** | 매매 포지션 (PENDING→ACTIVE→CLOSING→CLOSED) | UC-03, UC-04 |
| **Order** | 주문 이력 (매수/매도, 체결 상태) | UC-03, UC-04 |
| **TradeLog** | 포지션별 이벤트 이력 (시그널, 주문, 체결, 청산) | BR-O02 감사 추적 |
| **DailyReport** | 일일 성과 리포트 데이터 | UC-05 |
| **SystemLog** | 시스템 운영 로그 | BR-O04, BR-O05 |
| **ConfigHistory** | 설정 변경 이력 | UC-06, 감사 추적 |

---

## 9. 엔티티 정의

### 9.1 Position 상태 전이

```
               place_buy_order()          filled()
  (Signal) ───────► PENDING ──────────────► ACTIVE
                      │                       │
                      │ timeout/cancel()      │ place_sell_order()
                      ▼                       ▼
                   CANCELLED              CLOSING
                                             │
                                             │ filled()
                                             ▼
                                          CLOSED
```

| 상태 | 설명 | 진입 조건 |
|------|------|-----------|
| PENDING | 매수 주문 전송됨, 체결 대기 | 매수 주문 실행 시 |
| ACTIVE | 매수 체결 완료, 보유 중 | 매수 주문 체결 확인 시 |
| CLOSING | 매도 주문 전송됨, 체결 대기 | 청산 시그널 발생 시 |
| CLOSED | 매도 체결 완료, 청산 완료 | 매도 주문 체결 확인 시 |
| CANCELLED | 매수 주문 취소 (미체결 타임아웃) | 30분 미체결 시 |

---

## 10. 테이블 스키마 상세

### 10.1 universe (유니버스)

```sql
CREATE TABLE universe (
    stock_code    TEXT    PRIMARY KEY,            -- 종목코드 (6자리, 예: '005930')
    stock_name    TEXT    NOT NULL,               -- 종목명 (예: '삼성전자')
    market        TEXT    NOT NULL DEFAULT 'KOSPI', -- 시장구분
    sector        TEXT,                            -- 업종
    is_active     INTEGER NOT NULL DEFAULT 1,      -- 매매 대상 여부 (1: 활성, 0: 제외)
    updated_at    TEXT    NOT NULL                  -- 최종 업데이트 일시 (ISO8601)
);

CREATE INDEX idx_universe_active ON universe(is_active);
```

### 10.2 positions (포지션)

```sql
CREATE TABLE positions (
    position_id     TEXT    PRIMARY KEY,            -- UUID
    stock_code      TEXT    NOT NULL,               -- FK → universe.stock_code
    stock_name      TEXT    NOT NULL,               -- 종목명 (조회 편의)
    status          TEXT    NOT NULL DEFAULT 'PENDING', -- PENDING|ACTIVE|CLOSING|CLOSED|CANCELLED
    
    -- 진입 정보
    entry_price     REAL,                           -- 매수 체결 단가
    quantity        INTEGER NOT NULL,               -- 매수 수량
    entry_amount    REAL,                           -- 매수 총액 (entry_price × quantity)
    entry_date      TEXT,                           -- 매수 체결 일시
    entry_signal    TEXT,                           -- 진입 시그널 정보 (JSON)
    
    -- 청산 관리
    stop_loss_price   REAL,                         -- 손절가 (entry_price × 0.97)
    take_profit_price REAL,                         -- 익절가 (entry_price × 1.07)
    trailing_high     REAL,                         -- 보유 중 최고가 (트레일링 스탑용)
    trailing_stop_price REAL,                       -- 트레일링 스탑가 (trailing_high × 0.97)
    
    -- 청산 정보
    exit_price      REAL,                           -- 매도 체결 단가
    exit_date       TEXT,                           -- 매도 체결 일시
    exit_reason     TEXT,                           -- 청산 사유 (ES1~ES5)
    
    -- 손익
    pnl             REAL,                           -- 실현 손익 (원)
    pnl_pct         REAL,                           -- 실현 손익률 (%)
    
    -- 메타
    holding_days    INTEGER DEFAULT 0,              -- 보유 거래일 수
    created_at      TEXT    NOT NULL,               -- 레코드 생성 일시
    updated_at      TEXT    NOT NULL,               -- 최종 수정 일시
    
    FOREIGN KEY (stock_code) REFERENCES universe(stock_code)
);

CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_stock ON positions(stock_code);
CREATE INDEX idx_positions_entry_date ON positions(entry_date);
```

### 10.3 orders (주문)

```sql
CREATE TABLE orders (
    order_id        TEXT    PRIMARY KEY,            -- UUID (내부 주문 ID)
    position_id     TEXT    NOT NULL,               -- FK → positions.position_id
    stock_code      TEXT    NOT NULL,               -- 종목코드
    
    side            TEXT    NOT NULL,               -- BUY | SELL
    order_type      TEXT    NOT NULL,               -- MARKET | LIMIT
    status          TEXT    NOT NULL DEFAULT 'SUBMITTED', -- SUBMITTED|FILLED|PARTIALLY_FILLED|CANCELLED|REJECTED
    
    price           REAL,                           -- 주문가 (지정가인 경우)
    quantity        INTEGER NOT NULL,               -- 주문 수량
    filled_quantity INTEGER DEFAULT 0,              -- 체결 수량
    filled_price    REAL,                           -- 체결 단가
    filled_amount   REAL,                           -- 체결 총액
    
    broker_order_id TEXT,                           -- 증권사 주문번호 (한투 API 반환값)
    reject_reason   TEXT,                           -- 거부 사유
    
    retry_count     INTEGER DEFAULT 0,              -- 재시도 횟수
    
    created_at      TEXT    NOT NULL,               -- 주문 생성 일시
    submitted_at    TEXT,                           -- 주문 전송 일시
    filled_at       TEXT,                           -- 체결 일시
    cancelled_at    TEXT,                           -- 취소 일시
    
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
);

CREATE INDEX idx_orders_position ON orders(position_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at);
```

### 10.4 trade_logs (매매 이벤트 로그)

```sql
CREATE TABLE trade_logs (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id     TEXT,                           -- FK → positions.position_id (nullable)
    stock_code      TEXT,                           -- 종목코드
    
    event_type      TEXT    NOT NULL,               -- SIGNAL_DETECTED | RISK_CHECK_PASSED |
                                                    -- RISK_CHECK_FAILED | ORDER_SUBMITTED |
                                                    -- ORDER_FILLED | ORDER_CANCELLED |
                                                    -- ORDER_REJECTED | STOP_LOSS_TRIGGERED |
                                                    -- TAKE_PROFIT_TRIGGERED | TRAILING_STOP_TRIGGERED |
                                                    -- DAILY_LIMIT_HIT | MDD_LIMIT_HIT
    
    detail          TEXT,                           -- 이벤트 상세 (JSON)
    created_at      TEXT    NOT NULL,               -- 이벤트 발생 일시
    
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
);

CREATE INDEX idx_trade_logs_position ON trade_logs(position_id);
CREATE INDEX idx_trade_logs_type ON trade_logs(event_type);
CREATE INDEX idx_trade_logs_date ON trade_logs(created_at);
```

### 10.5 daily_reports (일일 리포트)

```sql
CREATE TABLE daily_reports (
    report_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date      TEXT    NOT NULL UNIQUE,        -- 거래일 (YYYY-MM-DD)
    
    -- 당일 매매 요약
    buy_count       INTEGER DEFAULT 0,              -- 매수 건수
    sell_count      INTEGER DEFAULT 0,              -- 매도 건수
    buy_amount      REAL    DEFAULT 0,              -- 매수 총액
    sell_amount     REAL    DEFAULT 0,              -- 매도 총액
    
    -- 손익
    realized_pnl    REAL    DEFAULT 0,              -- 실현 손익
    unrealized_pnl  REAL    DEFAULT 0,              -- 평가 손익
    total_pnl       REAL    DEFAULT 0,              -- 총 손익
    daily_return    REAL    DEFAULT 0,              -- 일일 수익률 (%)
    cumulative_return REAL  DEFAULT 0,              -- 누적 수익률 (%)
    
    -- 포트폴리오 상태
    active_positions INTEGER DEFAULT 0,             -- 보유 종목 수
    cash_balance    REAL    DEFAULT 0,              -- 현금 잔고
    total_value     REAL    DEFAULT 0,              -- 총 자산 (현금 + 평가금)
    
    -- 리스크 지표
    mdd             REAL    DEFAULT 0,              -- 최대 낙폭
    win_count       INTEGER DEFAULT 0,              -- 승 (당일 청산 기준)
    lose_count      INTEGER DEFAULT 0,              -- 패
    
    created_at      TEXT    NOT NULL                -- 리포트 생성 일시
);

CREATE UNIQUE INDEX idx_daily_reports_date ON daily_reports(trade_date);
```

### 10.6 config_history (설정 변경 이력)

```sql
CREATE TABLE config_history (
    history_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    param_key       TEXT    NOT NULL,               -- 변경된 파라미터 키 (예: 'strategy.stop_loss_pct')
    old_value       TEXT,                           -- 이전 값
    new_value       TEXT    NOT NULL,               -- 새 값
    changed_at      TEXT    NOT NULL                -- 변경 일시
);

CREATE INDEX idx_config_history_date ON config_history(changed_at);
```

### 10.7 system_logs (시스템 로그)

```sql
CREATE TABLE system_logs (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level           TEXT    NOT NULL,               -- DEBUG|INFO|WARNING|ERROR|CRITICAL
    module          TEXT    NOT NULL,               -- 모듈명 (예: 'order_executor')
    message         TEXT    NOT NULL,               -- 로그 메시지
    extra           TEXT,                           -- 추가 데이터 (JSON)
    created_at      TEXT    NOT NULL                -- 로그 생성 일시
);

CREATE INDEX idx_system_logs_level ON system_logs(level);
CREATE INDEX idx_system_logs_date ON system_logs(created_at);
```

---

# Part C: 인터페이스 설계

---

## 11. 외부 API 인터페이스

### 11.1 한투 API 엔드포인트 매핑

| 기능 | HTTP | 엔드포인트 | BRD 추적 | 사용 컴포넌트 |
|------|------|-----------|----------|---------------|
| 토큰 발급 | POST | `/oauth2/tokenP` | UC-01 | KISBroker.authenticate() |
| 현재가 조회 | GET | `/uapi/domestic-stock/v1/quotations/inquire-price` | UC-02, UC-04 | KISBroker.get_price() |
| 일봉 조회 | GET | `/uapi/domestic-stock/v1/quotations/inquire-daily-price` | UC-01 데이터 초기화 | KISBroker.get_ohlcv() |
| 매수 주문 | POST | `/uapi/domestic-stock/v1/trading/order-cash` | UC-03 | KISBroker.place_order() |
| 매도 주문 | POST | `/uapi/domestic-stock/v1/trading/order-cash` | UC-04 | KISBroker.place_order() |
| 주문 취소 | POST | `/uapi/domestic-stock/v1/trading/order-rvsecncl` | BR-B06 미체결 취소 | KISBroker.cancel_order() |
| 체결 조회 | GET | `/uapi/domestic-stock/v1/trading/inquire-daily-ccld` | UC-03, UC-04 | KISBroker.get_order_status() |
| 잔고 조회 | GET | `/uapi/domestic-stock/v1/trading/inquire-balance` | UC-01, UC-05 | KISBroker.get_balance() |

### 11.2 API 호출 공통 규약

```python
# 모든 한투 API 호출의 공통 헤더
headers = {
    "content-type": "application/json; charset=utf-8",
    "authorization": f"Bearer {self.token}",
    "appkey": self.app_key,
    "appsecret": self.app_secret,
    "tr_id": "<거래ID>",          # 각 API별 상이
    "custtype": "P",               # 개인
}

# Rate Limiter 적용 (NFR-P03: 초당 5건)
# 모든 API 호출 전 rate_limiter.acquire() 호출
```

### 11.3 토큰 관리

```
┌─────────────────────────────────────────────┐
│              토큰 생명주기                     │
│                                             │
│  발급 ─────► 사용(24H) ─────► 만료 ─────► 재발급 │
│                │                            │
│                ├─ 매 API 호출 전 만료 체크     │
│                └─ 만료 1시간 전 자동 갱신      │
└─────────────────────────────────────────────┘
```

---

## 12. 내부 모듈 인터페이스

### 12.1 핵심 데이터 클래스

```python
# common/types.py

@dataclass
class PriceData:
    """현재가 정보"""
    stock_code: str
    current_price: float
    open_price: float
    high_price: float
    low_price: float
    volume: int
    timestamp: str

@dataclass
class Order:
    """주문 요청"""
    order_id: str              # UUID
    position_id: str
    stock_code: str
    side: OrderSide            # BUY | SELL
    order_type: OrderType      # MARKET | LIMIT
    price: Optional[float]     # 지정가 (LIMIT인 경우)
    quantity: int

@dataclass  
class OrderResult:
    """주문 결과"""
    success: bool
    order_id: str
    broker_order_id: Optional[str]
    error_message: Optional[str]

@dataclass
class Portfolio:
    """포트폴리오 현황"""
    total_capital: float       # 총 투자금
    cash_balance: float        # 현금 잔고
    active_count: int          # 보유 종목 수
    daily_buy_amount: float    # 당일 누적 매수금액
    daily_pnl: float           # 당일 손익
    mdd: float                 # 최대 낙폭

@dataclass
class RiskCheckResult:
    """리스크 게이트 체크 결과"""
    passed: bool
    failed_gate: Optional[str]  # "RG1" ~ "RG4"
    reason: Optional[str]
```

### 12.2 Enum 정의

```python
# common/enums.py

from enum import Enum

class SystemState(Enum):
    INIT     = "INIT"
    READY    = "READY"
    RUNNING  = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED  = "STOPPED"
    ERROR    = "ERROR"

class PositionStatus(Enum):
    PENDING   = "PENDING"
    ACTIVE    = "ACTIVE"
    CLOSING   = "CLOSING"
    CLOSED    = "CLOSED"
    CANCELLED = "CANCELLED"

class OrderSide(Enum):
    BUY  = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT  = "LIMIT"

class OrderStatus(Enum):
    SUBMITTED        = "SUBMITTED"
    FILLED           = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED        = "CANCELLED"
    REJECTED         = "REJECTED"

class ExitReason(Enum):
    STOP_LOSS      = "ES1"
    TAKE_PROFIT    = "ES2"
    TRAILING_STOP  = "ES3"
    DEAD_CROSS     = "ES4"
    MAX_HOLDING    = "ES5"

class TradeEventType(Enum):
    SIGNAL_DETECTED        = "SIGNAL_DETECTED"
    RISK_CHECK_PASSED      = "RISK_CHECK_PASSED"
    RISK_CHECK_FAILED      = "RISK_CHECK_FAILED"
    ORDER_SUBMITTED        = "ORDER_SUBMITTED"
    ORDER_FILLED           = "ORDER_FILLED"
    ORDER_CANCELLED        = "ORDER_CANCELLED"
    ORDER_REJECTED         = "ORDER_REJECTED"
    STOP_LOSS_TRIGGERED    = "STOP_LOSS_TRIGGERED"
    TAKE_PROFIT_TRIGGERED  = "TAKE_PROFIT_TRIGGERED"
    TRAILING_STOP_TRIGGERED = "TRAILING_STOP_TRIGGERED"
    DAILY_LIMIT_HIT        = "DAILY_LIMIT_HIT"
    MDD_LIMIT_HIT          = "MDD_LIMIT_HIT"
```

---

## 13. 알림 인터페이스 (Telegram)

### 13.1 알림 유형 및 템플릿

| 유형 | 레벨 | 트리거 | 템플릿 |
|------|------|--------|--------|
| 기동 완료 | INFO | UC-01 완료 | `✅ ATS 기동 완료 \| 보유:{N}종목 \| 평가손익:{pnl}%` |
| 매수 주문 | INFO | UC-03 주문 전송 | `📈 매수 \| {종목} {수량}주 × {가격}원 \| 시그널: {signal}` |
| 매수 체결 | INFO | 체결 확인 | `✅ 매수 체결 \| {종목} {수량}주 × {체결가}원` |
| 매도 실행 | INFO | UC-04 매도 주문 | `📉 매도 \| {종목} {수량}주 \| {사유} \| 손익: {pnl}%` |
| 손절 발동 | WARNING | ES1 트리거 | `🔴 손절 \| {종목} {수량}주 \| {pnl}% \| 손실: {금액}원` |
| 일일 리포트 | INFO | UC-05 | (별도 리포트 포맷) |
| 일일 손실 한도 | CRITICAL | BR-R01 도달 | `⚠️ 일일 손실 한도 도달 ({pnl}%) \| 금일 매매 중단` |
| MDD 한도 | CRITICAL | BR-R02 도달 | `🚨 MDD 한도 도달 ({mdd}%) \| 시스템 일시 정지` |
| API 에러 | WARNING | 연속 실패 | `⚠️ API 에러 \| {endpoint} \| 재시도 {count}회 실패` |
| 시스템 에러 | CRITICAL | 치명적 에러 | `🚨 시스템 에러 \| {module} \| {message}` |
| 시스템 중지 | INFO | UC-08 완료 | `⛔ ATS 중지 \| 보유:{N}종목 \| 미체결:0건` |

---

# Part D: 배포 및 운영

---

## 14. 배포 아키텍처

### 14.1 실행 환경

```
┌──────────────────────────────────────────────┐
│              로컬 PC (Mac/Linux)              │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │           Python 3.11+ venv            │  │
│  │                                        │  │
│  │  ┌──────────┐    ┌─────────────────┐  │  │
│  │  │  main.py │    │  config.yaml    │  │  │
│  │  │  (ATS)   │    │  .env           │  │  │
│  │  └────┬─────┘    └─────────────────┘  │  │
│  │       │                                │  │
│  │       ├── data_store/ats.db (SQLite)   │  │
│  │       └── data_store/logs/             │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  OS crontab: 08:50 → python main.py start   │
│              16:00 → python main.py stop     │
│  (또는 systemd timer / launchd)              │
└──────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
   한투 REST API            Telegram Bot API
   (HTTPS)                  (HTTPS)
```

### 14.2 초기 설치 절차

```bash
# 1. 저장소 클론
git clone <repo_url> ats
cd ats

# 2. 가상환경 생성
python3.11 -m venv .venv
source .venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 환경변수 설정
cp .env.example .env
# .env 파일 편집: API 키, 텔레그램 토큰 입력

# 5. 설정 파일 확인
# config.yaml 파라미터 검토/수정

# 6. DB 초기화
python main.py init-db

# 7. 유니버스 초기 로드
python main.py update-universe

# 8. 모의투자 테스트
# .env에서 KIS_IS_PAPER=true 확인
python main.py start

# 9. 자동 기동 설정 (cron 예시)
# crontab -e
# 50 8 * * 1-5 cd /path/to/ats && .venv/bin/python main.py start
```

### 14.3 CLI 인터페이스

```
python main.py <command>

Commands:
  start              장중 매매 시스템 시작
  stop               시스템 중지 (미체결 정리 후)
  status             현재 시스템 상태, 보유 포지션 출력
  init-db            데이터베이스 초기화 (테이블 생성)
  update-universe    KOSPI200 유니버스 업데이트
  backtest           백테스트 실행
    --start DATE     시작일 (YYYY-MM-DD)
    --end DATE       종료일 (YYYY-MM-DD)
    --config FILE    설정 파일 경로 (기본: config.yaml)
  report             최근 N일 성과 리포트 출력
    --days N         조회 기간 (기본: 7)
```

---

## 15. 로깅 및 모니터링

### 15.1 로깅 정책

| 레벨 | 용도 | 예시 |
|------|------|------|
| DEBUG | 개발/디버깅 (운영 시 비활성) | 지표 계산 상세값, API 요청/응답 전문 |
| INFO | 정상 운영 이벤트 | 시그널 발생, 주문 전송, 체결 확인 |
| WARNING | 주의 필요 이벤트 | API 재시도, 데이터 누락 종목, 미체결 발생 |
| ERROR | 에러 발생 (복구 가능) | API 호출 실패, 주문 거부, DB 에러 |
| CRITICAL | 치명적 에러 (시스템 중단 가능) | 토큰 발급 불가, 연속 주문 실패, MDD 한도 도달 |

### 15.2 로그 로테이션

```
로그 파일: data_store/logs/ats_YYYY-MM-DD.log
보존 기간: 90일 (자동 삭제)
파일 크기: 일별 자동 분리 (날짜별)
포맷: [2026-02-25 09:31:15.123] [INFO] [strategy] 매수 시그널 발생: 삼성전자 (PS1+CF1)
```

### 15.3 모니터링 포인트

| # | 모니터링 항목 | 임계치 | 알림 방식 |
|---|-------------|--------|-----------|
| M1 | API 연속 실패 횟수 | 5회 | Telegram WARNING |
| M2 | 시그널 스캔 소요시간 | 60초 초과 (NFR-P01) | 로그 WARNING |
| M3 | 주문 → 전송 지연 | 5초 초과 (NFR-P02) | 로그 WARNING |
| M4 | 일일 손실률 | -3% (BR-R01) | Telegram CRITICAL |
| M5 | MDD | -10% (BR-R02) | Telegram CRITICAL |
| M6 | 미체결 주문 존재 | 매수 30분/매도 15분 | 로그 + 자동 처리 |
| M7 | 시스템 상태 이상 | ERROR 상태 진입 | Telegram CRITICAL |

---

# 부록

---

## 16. 추적 매트릭스

### 16.1 BRD → SAD 추적

| BRD 항목 | SAD 대응 | 설계 위치 |
|----------|----------|-----------|
| BRD 2.2 시그널 체계 | StrategyEngine (strategy/) | §5.2 |
| BRD 2.3 진입 시그널 | MomentumSwingStrategy.scan_entry_signals() | §5.2 |
| BRD 2.4 청산 시그널 | MomentumSwingStrategy.scan_exit_signals() | §5.2 |
| BRD 2.5 파라미터 | config.yaml | §7.1 |
| BRD 2.6 매매 타이밍 | Scheduler + SystemState | §5.1, §7.1 schedule |
| BRD 2.7 매수 수량 | OrderExecutor.execute_buy() | §5.4 |
| BRD 3.1 매수 규칙 (BR-B) | RiskManager + OrderExecutor | §5.3, §5.4 |
| BRD 3.2 매도 규칙 (BR-S) | OrderExecutor.execute_sell() | §5.4 |
| BRD 3.3 포트폴리오 규칙 (BR-P) | RiskManager.check_risk_gates() | §5.3 |
| BRD 3.4 리스크 규칙 (BR-R) | RiskManager | §5.3 |
| BRD 3.5 운영 규칙 (BR-O) | Scheduler + NotifierAdapter | §5.1, §13 |
| UC-01 시스템 기동 | Scheduler → MainLoop 초기화 시퀀스 | §6.1 |
| UC-02 시그널 스캔 | MainLoop.run_cycle() Phase 3 | §5.7, §6.2 |
| UC-03 매수 주문 | OrderExecutor.execute_buy() | §5.4, §6.2 |
| UC-04 포지션 모니터링 | MainLoop.run_cycle() Phase 1 | §5.7, §6.3 |
| UC-05 일일 리포트 | ReportGenerator | §5 (간접), §13 |
| UC-06 파라미터 변경 | ConfigManager + ConfigHistory | §7, §10.6 |
| UC-07 백테스트 | BacktestEngine (backtest/) | §4 디렉토리 구조 |
| UC-08 시스템 중지 | SystemStateManager STOPPING→STOPPED | §5.1 |
| NFR-E01 전략 확장 | BaseStrategy 추상 클래스 | §5.2 |
| NFR-E02 증권사 교체 | BaseBroker 추상 클래스 | §5.5 |
| NFR-E04 알림 채널 | BaseNotifier 추상 클래스 | §5.6 |
| NFR-P03 Rate Limit | KISBroker._rate_limiter | §5.5 |
| NFR-S01~S04 보안 | .env 분리, 토큰 메모리 관리 | §7.1, §11.3 |

### 16.2 테이블 → 유스케이스 추적

| 테이블 | 읽기 (R) | 쓰기 (W) | 유스케이스 |
|--------|----------|----------|-----------|
| universe | R | W | UC-01 (로드), UC-02 (스캔) |
| positions | R/W | W | UC-03 (생성), UC-04 (모니터링/갱신), UC-05 (리포트) |
| orders | R | W | UC-03 (매수), UC-04 (매도), UC-05 (집계) |
| trade_logs | R | W | 전 UC (이벤트 기록), UC-05 (리포트) |
| daily_reports | R | W | UC-05 (생성), UC-07 (백테스트 참조) |
| config_history | R | W | UC-06 (변경 기록) |
| system_logs | R | W | 전체 (운영 로그) |

---

## 17. 승인

### Phase 2 승인 체크리스트

| # | 항목 | 상태 |
|---|------|------|
| 1 | 아키텍처 스타일(3-Layer Monolith)에 동의한다 | ⬜ |
| 2 | 기술 스택(Python + SQLite + 한투API)을 확인했다 | ⬜ |
| 3 | 패키지 구조 및 디렉토리 레이아웃을 확인했다 | ⬜ |
| 4 | 컴포넌트 인터페이스(Strategy/Broker/Notifier)를 확인했다 | ⬜ |
| 5 | 시퀀스 다이어그램(기동/매수/청산)을 확인했다 | ⬜ |
| 6 | ERD 및 테이블 스키마를 확인했다 | ⬜ |
| 7 | 설정 파일 구조(config.yaml + .env)를 확인했다 | ⬜ |
| 8 | BRD → SAD 추적 매트릭스를 확인했다 | ⬜ |

### Phase Gate 2 통과 조건

| 조건 | 충족 여부 |
|------|-----------|
| 아키텍처 설계 완료 (SAD 작성) | ✅ |
| 데이터 모델 정의 완료 (ERD + 스키마) | ✅ |
| 외부 인터페이스 설계 완료 (한투 API 매핑) | ✅ |
| BRD 전 항목의 설계 대응 확인 (추적 매트릭스) | ✅ |
| PO 리뷰 완료 | ⬜ PO 리뷰 대기 |

> **다음 단계**: PO 승인 후 Phase 3(구현) 진입.
> Phase 3에서는 본 SAD를 기반으로 실제 코드를 작성한다.
> 구현 순서: Infrastructure → Data Access → Domain → Orchestrator (Bottom-Up)

---

*본 문서는 BRD(ATS-BRD-001)의 하위 문서이며, 변경 시 버전을 갱신한다.*
