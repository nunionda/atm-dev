import alphaStrategyMd from '@docs/alphaStrategy.md?raw';
import smcTheoryMd from '@docs/smcTheory.md?raw';
import tradingLogicFlowMd from '@docs/TradingLogicFlow.md?raw';
import mddDefenceMd from '@docs/mddDefenceStrategy.md?raw';
import exitStrategyMd from '@docs/ExitStrategyIndex.md?raw';
import trendTheoryMd from '@docs/trendTheory.md?raw';
import kellyMd from '@docs/Kelly Criterion.md?raw';
import scalpingMd from '@docs/scalpingPlaybook.md?raw';
import futuresStrategyMd from '@docs/futuresStrategy.md?raw';
import futureTradingMd from '@docs/future_trading_stratedy.md?raw';
import esScalpingMd from '@docs/es_scalping_strategy_v2.md?raw';
import kospi200FuturesMd from '@docs/kospi200_futures.md?raw';
import kospi200OptionsMd from '@docs/kospi200_options.md?raw';
import kospi200ConditionsMd from '@docs/kospi200_futures_conditions.md?raw';
import sp500FuturesMd from '@docs/sp500_futures.md?raw';
import blackScholesMd from '@docs/BlackScholesEquation.md?raw';
import optionCalcMd from '@docs/optionCalculator.md?raw';
import kospi200SimMd from '@docs/kospi200_futures_simulation.md?raw';
import kospi200SimReportMd from '@docs/kospi200_sim_report.md?raw';

export interface DocEntry {
  slug: string;
  title: string;
  description: string;
  category: string;
  content: string;
}

export interface DocCategory {
  key: string;
  label: string;
  labelKo: string;
  docs: DocEntry[];
}

export const categories: DocCategory[] = [
  {
    key: 'strategies',
    label: 'Core Strategies',
    labelKo: '핵심 전략',
    docs: [
      {
        slug: 'alpha-strategy',
        title: 'Alpha Strategy (6-Phase)',
        description: '모멘텀 스윙 6-Phase 파이프라인 — Sharpe 2.16-2.79',
        category: 'strategies',
        content: alphaStrategyMd,
      },
      {
        slug: 'smc-theory',
        title: 'Smart Money Concepts',
        description: 'BOS/CHoCH, Order Block, FVG, 4-Layer 스코어링',
        category: 'strategies',
        content: smcTheoryMd,
      },
      {
        slug: 'trading-logic-flow',
        title: 'Trading Logic Flow',
        description: '이론 → 구현 매핑 (Dow, Wyckoff, Elliott → Phase 0-5)',
        category: 'strategies',
        content: tradingLogicFlowMd,
      },
      {
        slug: 'mdd-defence',
        title: 'MDD Defence (7-Layer)',
        description: 'MDD 방어 7-Layer 아키텍처 — 최대 손실 제어',
        category: 'strategies',
        content: mddDefenceMd,
      },
    ],
  },
  {
    key: 'risk-exit',
    label: 'Risk & Exit',
    labelKo: '리스크 & 청산',
    docs: [
      {
        slug: 'exit-strategy',
        title: 'Exit Strategy Index',
        description: 'ATR/Structural/MA Stop, R-Multiple/Fibonacci TP',
        category: 'risk-exit',
        content: exitStrategyMd,
      },
      {
        slug: 'trend-theory',
        title: 'Trend Theory',
        description: '추세 판단 지표 — 매크로 4필터, MA/ADX/BB',
        category: 'risk-exit',
        content: trendTheoryMd,
      },
      {
        slug: 'kelly-criterion',
        title: 'Kelly Criterion',
        description: 'Kelly 공식 & 자산 배분 프레임워크',
        category: 'risk-exit',
        content: kellyMd,
      },
    ],
  },
  {
    key: 'specialized',
    label: 'Specialized Trading',
    labelKo: '전문 매매',
    docs: [
      {
        slug: 'scalping-playbook',
        title: 'Scalping Playbook',
        description: 'Fabio Valentini 스캘핑 — AMT 3-Stage, Triple-A Model',
        category: 'specialized',
        content: scalpingMd,
      },
      {
        slug: 'futures-strategy',
        title: 'Futures Strategy',
        description: 'Z-Score, Expected Value Engine, 통계 기반 진입',
        category: 'specialized',
        content: futuresStrategyMd,
      },
      {
        slug: 'futures-atr-trading',
        title: 'ATR Futures Trading',
        description: 'ATR 기반 선물 매매 — 동적 ATR Multiplier',
        category: 'specialized',
        content: futureTradingMd,
      },
      {
        slug: 'es-scalping-v2',
        title: 'ES/MES Scalping v2',
        description: 'ES/MES 통합 스캘핑 — 4-Layer, AMT + Z-Score',
        category: 'specialized',
        content: esScalpingMd,
      },
    ],
  },
  {
    key: 'products',
    label: 'Products & Models',
    labelKo: '상품 & 모델',
    docs: [
      {
        slug: 'kospi200-futures',
        title: 'KOSPI200 Futures',
        description: 'KOSPI200 선물 상품 규격 — 승수 250,000원',
        category: 'products',
        content: kospi200FuturesMd,
      },
      {
        slug: 'kospi200-options',
        title: 'KOSPI200 Options',
        description: 'KOSPI200 옵션 — European, Weekly, Black-Scholes',
        category: 'products',
        content: kospi200OptionsMd,
      },
      {
        slug: 'kospi200-conditions',
        title: 'KOSPI200 Futures Conditions',
        description: 'KOSPI200 & Mini KOSPI200 상세 비교',
        category: 'products',
        content: kospi200ConditionsMd,
      },
      {
        slug: 'sp500-futures',
        title: 'S&P500 Futures (ES/MES)',
        description: 'ES/MES 상품 규격 — $50/$5 승수, CME Globex',
        category: 'products',
        content: sp500FuturesMd,
      },
      {
        slug: 'black-scholes',
        title: 'Black-Scholes Equation',
        description: 'BS PDE, 콜/풋 가격 공식, Greeks',
        category: 'products',
        content: blackScholesMd,
      },
      {
        slug: 'option-calculator',
        title: 'Option Calculator',
        description: '옵션 계산기 아키텍처 (BS forward/inverse/Greeks)',
        category: 'products',
        content: optionCalcMd,
      },
    ],
  },
  {
    key: 'reports',
    label: 'Simulation Reports',
    labelKo: '시뮬레이션 리포트',
    docs: [
      {
        slug: 'kospi200-simulation',
        title: 'KOSPI200 Futures Simulation',
        description: 'K2IH2026 시뮬레이션 P&L 결과',
        category: 'reports',
        content: kospi200SimMd,
      },
      {
        slug: 'kospi200-sim-report',
        title: 'KOSPI200 Options Report',
        description: 'BS 옵션 분석 리포트 (HV 47.64%, ATM 가격)',
        category: 'reports',
        content: kospi200SimReportMd,
      },
    ],
  },
];

export const allDocs: DocEntry[] = categories.flatMap((c) => c.docs);

export function findDoc(category: string, slug: string): DocEntry | undefined {
  return allDocs.find((d) => d.category === category && d.slug === slug);
}

export function findCategory(key: string): DocCategory | undefined {
  return categories.find((c) => c.key === key);
}
