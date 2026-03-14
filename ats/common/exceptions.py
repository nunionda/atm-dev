"""
ATS 공통 예외 정의
"""


class ATSError(Exception):
    pass


class StateTransitionError(ATSError):
    pass


class ConfigError(ATSError):
    pass


class BrokerError(ATSError):
    pass
