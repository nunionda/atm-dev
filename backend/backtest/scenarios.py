"""
백테스트 시나리오 레지스트리.

위기 시기 및 주요 시장 국면별 사전 정의된 백테스트 기간을 관리한다.
각 시나리오는 warmup_start(MA200 워밍업용, 시작일 -1년)을 포함한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class BacktestScenario:
    """백테스트 시나리오 정의."""

    id: str
    name: str
    description: str
    start_date: str          # YYYYMMDD (실제 거래 시작일)
    end_date: str            # YYYYMMDD (거래 종료일)
    warmup_start: str        # start_date - ~1년 (MA200 워밍업용)
    markets: List[str]       # ["sp500", "ndx", "kospi"]
    character: str           # "severe_bear", "v_recovery", "grinding_bear" 등


# ── 사전 정의 시나리오 ──

SCENARIOS: Dict[str, BacktestScenario] = {
    "financial_crisis_us": BacktestScenario(
        id="financial_crisis_us",
        name="2008 금융위기 (US)",
        description="서브프라임 모기지 → 리먼 파산, S&P 500 -57% 하락. 극심한 하락장 방어력 검증.",
        start_date="20071001",
        end_date="20090331",
        warmup_start="20061001",
        markets=["sp500", "ndx"],
        character="severe_bear",
    ),
    "financial_crisis_kr": BacktestScenario(
        id="financial_crisis_kr",
        name="2008 금융위기 (KR)",
        description="글로벌 금융위기 KOSPI 연동 폭락. KOSPI -55% 하락.",
        start_date="20080101",
        end_date="20090331",
        warmup_start="20070101",
        markets=["kospi"],
        character="severe_bear",
    ),
    "covid_crash": BacktestScenario(
        id="covid_crash",
        name="COVID-19 급락",
        description="역사상 가장 빠른 약세장 진입(22일). V자 급락·회복 패턴.",
        start_date="20200201",
        end_date="20200630",
        warmup_start="20190201",
        markets=["sp500", "ndx", "kospi"],
        character="v_recovery",
    ),
    "rate_hike_2022": BacktestScenario(
        id="rate_hike_2022",
        name="2022 금리인상 약세장",
        description="Fed 공격적 긴축, 성장주→가치주 로테이션. S&P 500 -25%.",
        start_date="20220101",
        end_date="20221031",
        warmup_start="20210101",
        markets=["sp500", "ndx"],
        character="grinding_bear",
    ),
    "china_crash_2015": BacktestScenario(
        id="china_crash_2015",
        name="2015 차이나쇼크 (KR)",
        description="중국 경기둔화 + 위안화 절하, 신흥시장 스트레스.",
        start_date="20150601",
        end_date="20160229",
        warmup_start="20140601",
        markets=["kospi"],
        character="em_stress",
    ),
    "q4_correction_2018": BacktestScenario(
        id="q4_correction_2018",
        name="2018 Q4 급락",
        description="Fed 매파 발언 + 무역전쟁, S&P 500 -20% 급락 후 빠른 회복.",
        start_date="20180901",
        end_date="20190228",
        warmup_start="20170901",
        markets=["sp500", "ndx"],
        character="sharp_correction",
    ),
    "bull_run_2020": BacktestScenario(
        id="bull_run_2020",
        name="2020-21 상승장",
        description="COVID 회복 + 유동성 장세, 강세장 진입 시그널 생성 검증.",
        start_date="20200401",
        end_date="20211130",
        warmup_start="20190401",
        markets=["sp500", "ndx", "kospi"],
        character="strong_bull",
    ),
    "normal_2023": BacktestScenario(
        id="normal_2023",
        name="2023-24 보통장",
        description="2022 약세장 회복 → 혼합/횡보. 일반적 시장 환경 검증.",
        start_date="20230101",
        end_date="20241231",
        warmup_start="20220101",
        markets=["sp500", "ndx", "kospi"],
        character="mixed",
    ),
}


def get_scenario(scenario_id: str) -> BacktestScenario:
    """시나리오 ID로 조회. 'custom'은 직접 생성해야 함."""
    if scenario_id not in SCENARIOS:
        available = ", ".join(SCENARIOS.keys())
        raise ValueError(f"Unknown scenario: {scenario_id}. Available: {available}")
    return SCENARIOS[scenario_id]


def get_scenarios_for_market(market: str) -> Dict[str, BacktestScenario]:
    """특정 마켓에 해당하는 모든 시나리오 반환."""
    return {
        k: v for k, v in SCENARIOS.items()
        if market in v.markets
    }


def create_custom_scenario(
    start_date: str,
    end_date: str,
    markets: List[str],
) -> BacktestScenario:
    """사용자 지정 기간으로 커스텀 시나리오 생성."""
    # warmup: start_date - 1년
    warmup_year = int(start_date[:4]) - 1
    warmup_start = f"{warmup_year}{start_date[4:]}"

    return BacktestScenario(
        id="custom",
        name=f"Custom ({start_date[:4]}-{start_date[4:6]} ~ {end_date[:4]}-{end_date[4:6]})",
        description="사용자 지정 기간",
        start_date=start_date,
        end_date=end_date,
        warmup_start=warmup_start,
        markets=markets,
        character="custom",
    )
