/**
 * Glossary Data — 초보 트레이더를 위한 용어 사전
 * 48개 용어 + 7개 InfoCard 설명
 */

// ── Types ──────────────────────────────────────────────────────────

export interface GlossaryEntry {
  id: string;
  abbr: string;
  fullKR: string;
  fullEN: string;
  definition: string;
  formula?: string;
  tip?: string;
}

export interface InfoCardData {
  id: string;
  icon: string;
  titleKR: string;
  titleEN: string;
  body: string;
  tip?: string;
}

// ── Glossary (48 terms) ────────────────────────────────────────────

export const GLOSSARY: Record<string, GlossaryEntry> = {
  // ── ScalpAnalyzer — Price Data ──
  ohlc: {
    id: 'ohlc', abbr: 'OHLC', fullKR: '시가-고가-저가-종가', fullEN: 'Open-High-Low-Close',
    definition: '캔들 1봉의 4가지 가격. 시가(Open)=시작가, 고가(High)=최고가, 저가(Low)=최저가, 종가(Close)=마감가.',
  },
  atr: {
    id: 'atr', abbr: 'ATR', fullKR: '평균 실질 변동폭', fullEN: 'Average True Range',
    definition: '최근 14봉의 실제 변동 범위 평균. 변동성이 클수록 ATR이 크고, 손절 거리도 넓어집니다.',
    formula: 'ATR = avg(TR, 14)',
    tip: 'ATR × 1.0~1.5 = 스캘핑 손절 거리로 많이 씁니다.',
  },
  ma: {
    id: 'ma', abbr: 'MA', fullKR: '이동평균', fullEN: 'Moving Average',
    definition: '최근 N일간 종가의 평균. 추세 방향을 파악하는 기본 지표입니다. 가격이 MA 위면 상승추세, 아래면 하락추세 신호.',
  },
  sigma: {
    id: 'sigma', abbr: 'σ', fullKR: '표준편차', fullEN: 'Standard Deviation',
    definition: '가격이 평균에서 얼마나 흩어져 있는지를 나타냅니다. 값이 클수록 변동성이 크고, 작을수록 안정적입니다.',
    formula: 'σ = √(Σ(x-μ)²/N)',
  },
  trueRange: {
    id: 'trueRange', abbr: 'TR', fullKR: '실질 변동폭', fullEN: 'True Range',
    definition: '당일 고저차와 전일종가 대비 변동 중 최대값. 갭(Gap)도 반영하여 실제 변동성을 정확히 측정합니다.',
    formula: 'TR = max(H-L, |H-C\'|, |L-C\'|)',
  },

  // ── ScalpAnalyzer — Z-Score ──
  zscore: {
    id: 'zscore', abbr: 'Z', fullKR: 'Z-스코어', fullEN: 'Z-Score',
    definition: '현재가가 평균에서 표준편차 몇 배 떨어졌는지를 나타냅니다. |Z|>2 이면 95% 신뢰구간 밖으로, 평균회귀(되돌림) 가능성이 높습니다.',
    formula: 'Z = (Price - MA) / σ',
    tip: '|Z| ≥ 2: 강한 시그널 / |Z| ≥ 1.5: 보통 / |Z| < 1.5: 중립',
  },
  pvalue: {
    id: 'pvalue', abbr: 'P-Value', fullKR: '유의확률', fullEN: 'P-Value',
    definition: '현재 이탈이 우연일 확률입니다. P-Value가 작을수록(예: 0.05 이하) 통계적으로 의미 있는 이탈입니다.',
  },

  // ── ScalpAnalyzer — EV Engine ──
  ev: {
    id: 'ev', abbr: 'EV', fullKR: '기대값', fullEN: 'Expected Value',
    definition: '이 거래를 100번 반복했을 때 평균 예상 손익. 양수여야 수익 구조이고, 음수면 반복할수록 손실이 누적됩니다.',
    formula: 'EV = P(W)×W - P(L)×L - Cost',
    tip: 'EV > 0 확인 후 진입하면 장기적으로 유리합니다.',
  },
  friction: {
    id: 'friction', abbr: 'Friction', fullKR: '마찰비용', fullEN: 'Friction Cost',
    definition: '슬리피지(체결 미끄러짐) + 수수료를 틱 단위로 환산한 총 거래비용. 기대값에서 차감됩니다.',
    tip: '마찰비용이 Gross EV보다 크면 어떤 전략이든 손실 구조.',
  },
  rr: {
    id: 'rr', abbr: 'R:R', fullKR: '손익비', fullEN: 'Risk-Reward Ratio',
    definition: '평균이익 ÷ 평균손실. 예: 1.5:1이면 이길 때 지는 금액의 1.5배를 법니다. 1.5 이상이면 양호.',
  },
  tick: {
    id: 'tick', abbr: 'Tick', fullKR: '틱', fullEN: 'Tick',
    definition: '최소 가격 변동 단위. ES 1틱 = 0.25pt = $12.50. 수익/손실을 "틱 수"로 측정합니다.',
  },

  // ── ScalpAnalyzer — Kelly ──
  kelly: {
    id: 'kelly', abbr: 'Kelly', fullKR: '켈리 기준', fullEN: 'Kelly Criterion',
    definition: '확률과 손익비를 기반으로 최적의 베팅 비율을 산출하는 공식. 이론적 최적이지만 실전에서는 절반(Half Kelly)을 씁니다.',
    formula: 'f* = (b×p - q) / b',
  },
  halfKelly: {
    id: 'halfKelly', abbr: '½K', fullKR: '하프 켈리', fullEN: 'Half Kelly',
    definition: '켈리의 절반. 실전의 불확실성(데이터 오차, 감정)을 감안한 보수적 베팅 비율. 프로 트레이더 대부분이 사용합니다.',
    tip: '풀 켈리의 50% = 변동 줄이면서도 장기 성장률 극대화.',
  },
  conviction: {
    id: 'conviction', abbr: '-', fullKR: '확신도', fullEN: 'Conviction Level',
    definition: '켈리 값 기반의 우위 등급. NO EDGE(우위 없음) → VERY LOW → LOW → MODERATE → HIGH → VERY HIGH 순서입니다.',
  },

  // ── ScalpAnalyzer — Position & Stops ──
  sl: {
    id: 'sl', abbr: 'SL', fullKR: '손절선', fullEN: 'Stop Loss',
    definition: '손실 제한을 위해 미리 정한 청산가. 이 가격에 도달하면 무조건 손실을 확정하고 빠져나옵니다.',
    tip: '손절선은 반드시 진입 전에 정하고, 절대 뒤로 밀지 않습니다.',
  },
  tp: {
    id: 'tp', abbr: 'TP', fullKR: '익절선', fullEN: 'Take Profit',
    definition: '이익 확정을 위해 미리 정한 청산가. 이 가격에 도달하면 수익을 확정합니다.',
  },
  rrNotation: {
    id: 'rrNotation', abbr: '1R/2R/3R', fullKR: 'R 배수', fullEN: 'R-Multiple',
    definition: '손절폭(=1R) 대비 익절 목표 배수. 예: 1.5R = 손절폭의 1.5배를 목표. 2R = 2배 목표.',
  },

  // ── ScalpAnalyzer — Basis & Account ──
  contango: {
    id: 'contango', abbr: 'Contango', fullKR: '콘탱고', fullEN: 'Contango',
    definition: '선물가 > 현물가인 상태. 보유비용(금리, 보관료)이 반영된 정상적인 상태입니다. 만기 수렴 시 선물에 하방압력이 생깁니다.',
  },
  backwardation: {
    id: 'backwardation', abbr: 'Backwrd.', fullKR: '백워데이션', fullEN: 'Backwardation',
    definition: '선물가 < 현물가인 상태. 시장 스트레스/공급 부족 시그널. 차익매수세(프로그램)가 유입될 수 있습니다.',
  },
  basis: {
    id: 'basis', abbr: 'Basis', fullKR: '베이시스', fullEN: 'Basis Spread',
    definition: '선물가 - 현물가 차이. 양수면 콘탱고, 음수면 백워데이션, 0 근처면 적정가(Fair Value)입니다.',
  },
  initialMargin: {
    id: 'initialMargin', abbr: 'IM', fullKR: '개시증거금', fullEN: 'Initial Margin',
    definition: '포지션을 열 때 필요한 최소 보증금. 계좌 잔고가 이 금액 이상이어야 1계약을 살 수 있습니다.',
  },
  maintMargin: {
    id: 'maintMargin', abbr: 'MM', fullKR: '유지증거금', fullEN: 'Maintenance Margin',
    definition: '포지션 유지 최소 잔고. 잔고가 이 이하로 떨어지면 마진콜(추가 입금 요구)이 발생합니다.',
  },
  notional: {
    id: 'notional', abbr: '-', fullKR: '명목가치', fullEN: 'Notional Value',
    definition: '1계약이 대표하는 총 금액. 현재가 × 승수(multiplier)로 계산합니다. 실제 투자 노출 규모입니다.',
  },

  // ── FabioStrategy — AMT ──
  amt: {
    id: 'amt', abbr: 'AMT', fullKR: '경매시장이론', fullEN: 'Auction Market Theory',
    definition: '시장을 매수자와 매도자의 "경매장"으로 보는 분석법. 가격이 가치 있는 수준(Value Area) 안에서 거래되는지 벗어나는지를 판단합니다.',
  },
  vah: {
    id: 'vah', abbr: 'VAH', fullKR: '가치상한', fullEN: 'Value Area High',
    definition: 'Value Area 상단 경계 (MA + 1σ). 여기 위로 가격이 올라가면 "비싼 영역"이며, 매도 압력이 높아질 수 있습니다.',
  },
  val: {
    id: 'val', abbr: 'VAL', fullKR: '가치하한', fullEN: 'Value Area Low',
    definition: 'Value Area 하단 경계 (MA - 1σ). 여기 아래로 가격이 내려가면 "싼 영역"이며, 매수 기회일 수 있습니다.',
  },
  poc: {
    id: 'poc', abbr: 'POC', fullKR: '거래집중가', fullEN: 'Point of Control',
    definition: '가장 많이 거래된 가격대 (MA 근사). 시장 참여자들이 합의한 "공정가격"으로, 가격이 이곳으로 되돌아오는 경향이 있습니다.',
  },
  lvn: {
    id: 'lvn', abbr: 'LVN', fullKR: '거래희박구간', fullEN: 'Low Volume Node',
    definition: '거래가 거의 없었던 가격대. 가격이 이 구간을 빠르게 통과하는 경향이 있어, 진입/탈출 포인트로 활용됩니다.',
  },
  balance: {
    id: 'balance', abbr: '-', fullKR: '균형', fullEN: 'Balance',
    definition: 'Value Area 안에서 횡보하는 상태. 매수/매도 세력이 팽팽해서 가격이 범위 안에서 움직입니다.',
    tip: '균형 → 평균회귀(Mean Reversion) 전략이 유리.',
  },
  imbalance: {
    id: 'imbalance', abbr: '-', fullKR: '불균형', fullEN: 'Imbalance',
    definition: 'Value Area 밖으로 이탈한 상태. 한쪽 세력이 우세하여 가격이 방향성을 갖습니다.',
    tip: '불균형 → 추세추종(Trend Continuation) 전략이 유리.',
  },

  // ── FabioStrategy — Triple-A ──
  absorption: {
    id: 'absorption', abbr: 'A1', fullKR: '흡수', fullEN: 'Absorption',
    definition: '큰 매도(또는 매수)를 반대쪽이 흡수하는 현상. 캔들에 긴 꼬리(wick)가 나타나는 것이 특징입니다.',
    tip: '긴 꼬리 = 누군가 그 가격에서 대량 매수/매도로 받아냈다는 증거.',
  },
  accumulation: {
    id: 'accumulation', abbr: 'A2', fullKR: '축적', fullEN: 'Accumulation',
    definition: '좁은 범위에서 조용히 포지션을 모으는 단계. 캔들 봉이 짧고 거래량이 줄어드는 것이 특징입니다.',
    tip: '축적이 길수록 이후 움직임(Aggression)이 강한 경향.',
  },
  aggression: {
    id: 'aggression', abbr: 'A3', fullKR: '공격', fullEN: 'Aggression',
    definition: '큰 몸통의 방향성 봉. 축적 완료 후 한쪽 세력이 강하게 밀어붙이는 단계입니다.',
  },

  // ── FabioStrategy — Grade & Session ──
  confluence: {
    id: 'confluence', abbr: '-', fullKR: '컨플루언스', fullEN: 'Confluence',
    definition: '여러 분석 조건이 동시에 충족되는 것. 컨플루언스가 많을수록 시그널의 신뢰도가 높습니다.',
    tip: '6개 중 5개 이상 = Grade A (최고 확신도).',
  },
  riskTier: {
    id: 'riskTier', abbr: '-', fullKR: '리스크 등급', fullEN: 'Risk Tier',
    definition: 'MAX/HALF/QUARTER. 현재 상황에 따른 포지션 크기 배율. 연속 손실 등 상황에 따라 자동으로 축소됩니다.',
  },
  scratch: {
    id: 'scratch', abbr: '-', fullKR: '스크래치', fullEN: 'Scratch',
    definition: '거의 본전 수준에서 청산한 거래. 큰 수익도 손실도 없는 중립적 결과입니다.',
  },
  cvd: {
    id: 'cvd', abbr: 'CVD', fullKR: '누적거래량차이', fullEN: 'Cumulative Volume Delta',
    definition: '매수체결량 - 매도체결량의 누적합. 실제 주문흐름 방향을 보여줍니다. CVD 상승 = 매수 우세.',
  },
  be: {
    id: 'be', abbr: 'BE', fullKR: '본전', fullEN: 'Break Even',
    definition: '진입가 수준. 손절선을 진입가로 올리면 리스크가 제거(free trade)됩니다.',
  },

  // ── FabioStrategy — Backtest ──
  profitFactor: {
    id: 'profitFactor', abbr: 'PF', fullKR: '수익팩터', fullEN: 'Profit Factor',
    definition: '총수익 ÷ 총손실. 1.5 이상이면 양호, 1.0 이하면 손실 구조입니다.',
    formula: 'PF = 총수익 / 총손실',
    tip: 'PF 1.5 이상 + 충분한 거래 횟수 = 신뢰할 수 있는 전략.',
  },
  sharpe: {
    id: 'sharpe', abbr: 'SR', fullKR: '샤프비율', fullEN: 'Sharpe Ratio',
    definition: '수익률 ÷ 변동성. 위험 대비 보상 효율을 나타냅니다. 1 이상이면 양호.',
    formula: 'SR = 평균수익 / 수익표준편차',
  },
  maxDD: {
    id: 'maxDD', abbr: 'MDD', fullKR: '최대낙폭', fullEN: 'Maximum Drawdown',
    definition: '자산 고점에서 저점까지 최대 하락폭. 최악의 시나리오를 보여줍니다.',
    tip: 'MDD가 계좌의 감내 한계를 넘지 않도록 리스크 관리.',
  },
  equityCurve: {
    id: 'equityCurve', abbr: '-', fullKR: '자산곡선', fullEN: 'Equity Curve',
    definition: '거래 누적 손익 그래프. 우상향이면 전략이 양호하고, 우하향이면 전략 점검이 필요합니다.',
  },

  // ── Additional ──
  multiplier: {
    id: 'multiplier', abbr: '-', fullKR: '승수', fullEN: 'Multiplier',
    definition: '포인트당 달러(원) 가치. ES 승수 50 = 1포인트 이동 시 $50 손익.',
  },
  tickValue: {
    id: 'tickValue', abbr: '-', fullKR: '틱 가치', fullEN: 'Tick Value',
    definition: '1틱(최소 가격변동) 이동 시 손익. ES: 1틱 = 0.25pt = $12.50.',
  },
};

// ── InfoCard Data (7 cards) ────────────────────────────────────────

export const INFO_CARDS: Record<string, InfoCardData> = {
  zscore: {
    id: 'zscore',
    icon: '📐',
    titleKR: 'Z-스코어란?',
    titleEN: 'Z-Score',
    body: '가격이 평균에서 얼마나 떨어졌는지를 표준편차 단위로 측정합니다.\n\n'
      + '• |Z| < 1: 정상 범위 (68% 확률)\n'
      + '• |Z| 1~2: 약간 이탈 (68~95%)\n'
      + '• |Z| > 2: 강한 이탈 (95% 밖) → 되돌림 가능성↑\n\n'
      + '양수 Z = 평균보다 높음(비쌈) → 숏 유리\n'
      + '음수 Z = 평균보다 낮음(쌈) → 롱 유리',
    tip: '68-95-99.7 규칙: 가격의 68%는 ±1σ, 95%는 ±2σ, 99.7%는 ±3σ 안에 있습니다.',
  },
  evEngine: {
    id: 'evEngine',
    icon: '⚡',
    titleKR: '기대값 엔진이란?',
    titleEN: 'EV Engine',
    body: '동전 던지기처럼 생각하세요:\n\n'
      + '• 앞면(승리) 나올 확률 × 이길 때 금액\n'
      + '• 뒷면(패배) 나올 확률 × 질 때 금액\n'
      + '• 여기서 비용(수수료+슬리피지)을 빼면 = 순 기대값\n\n'
      + '예: 승률 58%, 이익 6t, 손실 4t, 비용 0.68t\n'
      + '→ 0.58×6 - 0.42×4 - 0.68 = +1.12t (수익 구조)',
    tip: '승률이 40%여도 손익비(R:R)가 크면 EV 양수 가능! 핵심은 승률이 아니라 기대값입니다.',
  },
  kellyCriterion: {
    id: 'kellyCriterion',
    icon: '🎰',
    titleKR: '켈리 기준이란?',
    titleEN: 'Kelly Criterion',
    body: '카지노에서 유리한 게임을 찾았다면, 매번 얼마를 걸어야 할까?\n\n'
      + '공식: f* = (b×p - q) / b\n'
      + '• p = 승률, q = 패율(1-p)\n'
      + '• b = 손익비(평균이익 ÷ 평균손실)\n\n'
      + '• f* > 0: 우위 있음 → 비율만큼 베팅\n'
      + '• f* ≤ 0: 우위 없음 → 베팅하지 말 것',
    tip: '풀 켈리는 변동이 너무 크므로, 실전에서는 반(Half Kelly)만 사용합니다. 장기 성장률의 75%를 유지하면서 변동은 절반으로 줄입니다.',
  },
  basisSpread: {
    id: 'basisSpread',
    icon: '📉',
    titleKR: '선현물 스프레드란?',
    titleEN: 'Basis Spread',
    body: '선물가와 현물가의 차이입니다.\n\n'
      + '• 콘탱고(선물>현물): 정상 상태. 보유비용(금리)이 반영되어 선물이 비쌉니다.\n'
      + '• 백워데이션(선물<현물): 시장 스트레스. 즉시 수요가 급증하면 현물이 더 비싸집니다.\n'
      + '• Fair Value(≈0): 차익거래 유인이 없는 적정 수준.',
    tip: '큰 백워데이션은 프로그램 매수세(차익거래) 유입 시그널. 스캘핑 롱 진입 근거가 될 수 있습니다.',
  },
  amtFilter: {
    id: 'amtFilter',
    icon: '🏛️',
    titleKR: 'AMT 3단계 필터란?',
    titleEN: 'Auction Market Theory 3-Step Filter',
    body: '시장을 "경매장"으로 보는 분석법입니다.\n\n'
      + '① 시장 상태: 균형(Balance) vs 불균형(Imbalance)\n'
      + '  → 균형 = 박스권 횡보, 불균형 = 방향성 이탈\n\n'
      + '② 가격 위치: Value Area(적정가 구간) 대비 현재 위치\n'
      + '  → VAH(상한), POC(중심), VAL(하한) 기준 판단\n\n'
      + '③ 공격성: 방향성 있는 큰 봉이 나타나는지 확인\n'
      + '  → 3단계 모두 충족 시 "ALL PASS"',
    tip: '균형 상태 → 평균회귀(되돌림) 전략 / 불균형 상태 → 추세추종 전략을 선택합니다.',
  },
  tripleA: {
    id: 'tripleA',
    icon: '🔷',
    titleKR: 'Triple-A란?',
    titleEN: 'Triple-A (Absorption-Accumulation-Aggression)',
    body: '파도처럼 3단계로 진행됩니다:\n\n'
      + '🛡️ 흡수(Absorption): 파도가 밀려와도 방파제가 버티듯, 큰 매도를 매수가 받아냅니다.\n'
      + '  → 긴 꼬리(wick) 캔들이 특징\n\n'
      + '📦 축적(Accumulation): 조용한 바다처럼, 좁은 범위에서 세력이 포지션을 모읍니다.\n'
      + '  → 짧은 봉, 줄어드는 거래량\n\n'
      + '⚡ 공격(Aggression): 쓰나미처럼, 축적된 에너지가 한 방향으로 폭발합니다.\n'
      + '  → 큰 몸통 방향성 봉',
    tip: '3단계 모두 감지 = Full Alignment → 최고 확신도(Grade A) 자동 부여.',
  },
  setupGrade: {
    id: 'setupGrade',
    icon: '⭐',
    titleKR: '셋업 등급이란?',
    titleEN: 'Setup Grade',
    body: '6개 조건(컨플루언스)의 충족 수로 등급을 매깁니다:\n\n'
      + '• Grade A (5~6개): 최고 확신도 → 풀 리스크(100%)\n'
      + '• Grade B (3~4개): 중간 확신도 → 절반 리스크(50%)\n'
      + '• Grade C (2개): 낮은 확신도 → 25% 리스크\n'
      + '• Grade D (0~1개): 조건 미충족 → 거래하지 않음\n\n'
      + '6개 조건: Z-Score 방향성, EV 양수, AMT 통과,\n'
      + 'Triple-A 감지, 모델 선택, 가격 위치 적정',
    tip: '등급이 높을수록 계약 수가 많아집니다. Grade D면 무조건 관망!',
  },
};
