# ATS (Automated Trading System)

## 프로젝트 개요
KOSPI200 모멘텀 스윙 자동매매 시스템.
Python 3.11+, SQLite, 한국투자증권 API, Telegram 알림.

## 아키텍처
3-Layer Monolith: Orchestrator(core/) → Domain(strategy/,risk/,order/,position/) → Infra(infra/)

## 핵심 규칙
- 손절 -3% 절대 불변 (BR-S01)
- 일일 손실 -3% 도달 시 매매 중단 (BR-R01)
- MDD -10% 도달 시 시스템 정지 (BR-R02)
- 최대 10종목, 종목당 15%, 최소 현금 20%

## 설정
- config.yaml: 전략 파라미터
- .env: API Key, 계좌번호 (절대 커밋 금지)

## 진입 시그널
PS1(골든크로스) + PS2(MACD) → CF1(RSI) + CF2(거래량) → RG1~RG4(리스크 게이트)

## 청산 우선순위
ES1(손절-3%) > ES2(익절+7%) > ES3(트레일링-3%) > ES4(데드크로스) > ES5(보유10일)

## 테스트
python run_tests.py          # 독립 단위 테스트 43건
pytest tests/ -v             # pytest 전체 (SQLAlchemy 필요)

## 주요 파일
- main.py: 엔트리포인트 (start, status, init-db)
- core/main_loop.py: 4-Phase 매매 루프
- strategy/momentum_swing.py: 전략 엔진
- infra/broker/kis_broker.py: 한투 API
- scripts/health_check.py: 헬스체크
- scripts/paper_trade_test.py: 모의투자 연동 테스트

## 현재 상태
Phase 0~5 문서 완료. 코드 3,799 LOC. 단위 테스트 43건 PASS.
다음: Python venv 설정 → .env 입력 → health_check → paper_trade_test
