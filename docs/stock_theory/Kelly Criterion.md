# Trading Strategy Framework: Kelly Criterion & Asset Allocation

이 문서는 켈리 공식(Kelly Criterion)을 기반으로 한 자산 배분 및 주식 포트폴리오 전략 최적화 가이드를 정의한다.

## 1. Core Principles (핵심 원칙)
- **Survival First:** 파산 위험(Risk of Ruin)을 0으로 유지하기 위해 Fractional Kelly를 적용한다.
- **Dynamic Rebalancing:** 각 자산군과 전략의 승률(p) 및 손익비(b)에 따라 비중을 동적으로 조절한다.
- **Role Isolation:** 주식, 선물, 옵션의 위험 프로필을 분리하여 관리한다.

## 2. Global Asset Allocation (자산군별 배분)
전체 원금 대비 투입 비중은 자산의 변동성에 반비례하도록 설계한다.

| Asset Type | Kelly Coefficient (f) | Description |
| :--- | :--- | :--- |
| **Cash & Equity** | 0.5 (Half-Kelly) | 기본 자산군, 장기 추세 및 복리 효과 극대화 |
| **Futures** | 0.2 ~ 0.3 | 레버리지 리스크 대응을 위한 보수적 접근 |
| **Options** | 0.1 이하 | 고위험 자산으로, 원금 보호를 위해 최소 비중 유지 |

### Calculation Formula
`f* = (bp - q) / b`
- `b`: 손익비 (Profit/Loss Ratio)
- `p`: 승률 (Win Rate)
- `q`: 패배 확률 (1 - p)
- **Final Weight:** `f* * Kelly Coefficient`

## 3. Stock Portfolio Strategy (주식 내부 전략)
주식 자산 내에서는 시장 국면(Market Regime)에 따라 '추세', '스윙', '단기' 전략의 비율을 산정한다.

### Strategy Profiles
1. **Trend Following (추세):** Core Strategy
   - 목적: 큰 추세 수익 확정
   - 권장 비중: 40% (변동성이 낮고 손익비가 높을 때 확장)
2. **Swing (스윙):** Satellite Strategy
   - 목적: 중기 파동 매매
   - 권장 비중: 40% (기술적 분석 및 모멘텀 기반)
3. **Scalping (단기):** Active Strategy
   - 목적: 현금 흐름 창출 및 시장 감각 유지
   - 권장 비중: 20% (높은 승률 기반, 자금 회전 중심)

## 4. Implementation Logic (구현 로직)
AI 에이전트나 시스템이 비중을 계산할 때 다음 알고리즘을 따른다.

```pseudo
function calculate_allocation(strategy_data):
    kelly_raw = (data.b * data.p - data.q) / data.b
    safe_kelly = kelly_raw * strategy_data.risk_coefficient
    return clamp(safe_kelly, 0, strategy_data.max_cap)

// 주식 내 비율 정규화
total_equity_weight = trend_w + swing_w + scalp_w
normalized_trend = (trend_w / total_equity_weight) * 0.8 // 20%는 현금 예비비

---

**전문가 코멘트:**
"마음의 문 대신 열어줄 순 없지만 두드릴 수는 있다"는 말씀처럼, 이 수식과 체계는 시장의 수익을 강제로 가져다주지는 않지만, 시장이 기회를 줄 때 **준비된 상태(Ready-state)**로 있게 해주는 강력한 도구가 될 것입니다. 클로드 코드에 이 파일을 컨텍스트로 제공하면, 매매 일지 분석이나 비중 추천 시 매우 정교한 피드백을 받으실 수 있습니다.