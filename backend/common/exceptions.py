"""
ATS 커스텀 예외 클래스
문서: ATS-SAD-001
"""


class ATSError(Exception):
    """ATS 기본 예외"""
    pass


class BrokerError(ATSError):
    """브로커 API 관련 에러"""
    pass


class AuthenticationError(BrokerError):
    """인증 실패 (토큰 발급 등)"""
    pass


class OrderError(BrokerError):
    """주문 실패"""
    pass


class OrderRejectedError(OrderError):
    """주문 거부 (잔고 부족 등)"""
    pass


class RateLimitError(BrokerError):
    """API 호출 제한 초과"""
    pass


class DataError(ATSError):
    """데이터 조회/처리 에러"""
    pass


class RiskLimitError(ATSError):
    """리스크 한도 도달"""
    pass


class DailyLossLimitError(RiskLimitError):
    """일일 손실 한도 도달 (BR-R01)"""
    pass


class MDDLimitError(RiskLimitError):
    """MDD 한도 도달 (BR-R02)"""
    pass


class ConfigError(ATSError):
    """설정 파일 오류"""
    pass


class StateTransitionError(ATSError):
    """잘못된 시스템 상태 전이"""
    pass
