# ATM-DEV: Automated Trading System (ATS) & Analytics Dashboard

## 🎯 프로젝트 목표 (Project Goals)
본 프로젝트는 **KOSPI200 및 주식/선물 시장을 타겟으로 하는 자동 매매 시스템(ATS)과 이를 모니터링/분석하기 위한 프론트엔드 대시보드**를 구축하는 것을 목표로 합니다.
1. **백엔드 (ATS Engine)**: 모멘텀 스윙 전략을 기반으로 한 자동 매매 로직, 리스크 관리, 한국투자증권(KIS) API 연동 및 백테스팅/시뮬레이션 기능 제공
2. **프론트엔드 (Web Dashboard)**: 실시간 트레이딩 차트, 포트폴리오 상태, 리스크 게이트 관리, 매매 일지(Trading Journal) 등을 단일 뷰에서 통합적으로 모니터링할 수 있는 직관적인 UI 제공

---

## 🚀 진행 사항 및 커밋 내역 (Commit Progress)
- **Git Repository 초기화**: 루트 디렉토리 및 서브모듈 계층 Git 세팅 완료 (`git init`)
- **Initial Commit 완료**: 기존에 작성된 `stock_theory` 문서(선물 매매 전략 등), `design_plan`, `ats` 모듈 및 `web` 프론트엔드 구성요소 일괄 커밋
- **기능 업데이트 내역**:
  - `web`: 차트 드로잉 툴(Drawing Tools), Subcharts 토글 기능 등 Dashboard UI 리팩토링 및 기능 완비
  - `ats`: 모멘텀 스윙 규칙, 리스크 관리(손절 -3%, 일일 손실 -3% 컷 등), API, Analytics, Simulation 모듈 추가
  - 병합 충돌 해결: `.gitignore` 파일의 로컬/서브모듈 머지 컨플릭트 영구 해결

---

## 🛠 시스템 아키텍처 및 서버 구축 현황

### 1. 백엔드 서버 (ats/)
백엔드는 3-Layer Monolith 아키텍처로 구성되어 있으며 매매 신호 탐지, 주문 실행, 계좌 관리를 담당합니다.
* **기술 스택**: Python 3.11+, SQLite (SQLAlchemy), KIS API
* **주요 모듈**:
  - `core/`: Orchestrator (메인 매매 루프)
  - `strategy/`, `risk/`, `order/`, `position/`: 도메인 로직 (진입/청산 룰 및 위험 관리)
  - `api/`, `analytics/`, `simulation/`: 백테스트 및 프론트엔드 연동용 API
* **진행 상태**: Phase 0~5 설계 문서 완료, 단위 테스트(UnitTest) 43건 PASS, 시뮬레이터 및 API 라우터 구축 완료.

### 2. 프론트엔드 서버 (web/)
프론트엔드는 트레이더 관점에서 최적화된 시각적 통찰력(Market Regime, Volatility Profile, Signal Analysis 등)을 제공합니다.
* **기술 스택**: React 18, TypeScript, Vite, Recharts, Lucide Icons
* **주요 구성 요소**:
  - `Dashboard`: 캔들스틱/라인/하이킨아시 차트, SR(Support/Resistance) 레벨, 측정 도구(Measure) 및 드로잉 오버레이
  - `Performance` & `Risk`: 수익률 곡선, 리스크 이벤트 로그, 트레이딩 저널
* **진행 상태**: 대시보드 UI/UX 리팩토링 및 통합(Unified View) 완료, 컴포넌트 모듈화 적용 완료.

---

## 📖 프로젝트 운영 매뉴얼 (How to Run)

본 애플리케이션은 프론트엔드와 백엔드를 각각 독립적으로 실행해야 합니다.

### API 서버 실행 (Backend)
ATS 디렉토리로 이동하여 가상환경을 활성화하고 서버를 실행합니다.
```bash
# 1. ats 디렉토리로 이동
cd ats/

# 2. 가상환경 활성화 및 의존성 설치 (최초 1회)
# python3 -m venv venv
# source venv/bin/activate
# pip install -r requirements.txt

# 3. API 서버 실행
python main.py api
```
> **참고**: 매매 로직만 쉘에서 실행하려면 `python main.py start` 커맨드를 사용합니다. 데이터베이스 초기화는 `python main.py init-db` 입니다. (.env 파일에 API 키 필수 세팅)

### 웹 대시보드 실행 (Frontend)
web 디렉토리로 이동하여 Vite 개발 서버를 구동합니다.
```bash
# 1. web 디렉토리로 이동
cd web/

# 2. 패키지 설치 (최초 1회)
# npm install

# 3. 개발 서버 실행
npm run dev
```
> 서버가 정상적으로 실행되면 브라우저에서 `http://localhost:5173` (기본 포트)로 접속하여 대시보드를 확인할 수 있습니다.
