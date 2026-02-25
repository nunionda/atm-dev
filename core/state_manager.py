"""
시스템 상태 관리
문서: ATS-SAD-001 §5.1 (상태 다이어그램)

상태 전이: INIT → READY → RUNNING → STOPPING → STOPPED
           어느 상태에서든 → ERROR (치명적 에러)
"""

from __future__ import annotations

from common.enums import SystemState
from common.exceptions import StateTransitionError
from infra.logger import get_logger

logger = get_logger("state_manager")

# 유효한 상태 전이 규칙 (SAD §5.1 상태 전이 테이블)
VALID_TRANSITIONS = {
    SystemState.INIT: {SystemState.READY, SystemState.ERROR},
    SystemState.READY: {SystemState.RUNNING, SystemState.STOPPED, SystemState.ERROR},
    SystemState.RUNNING: {SystemState.STOPPING, SystemState.ERROR},
    SystemState.STOPPING: {SystemState.STOPPED, SystemState.ERROR},
    SystemState.STOPPED: {SystemState.INIT, SystemState.ERROR},
    SystemState.ERROR: {SystemState.READY, SystemState.INIT},
}


class SystemStateManager:
    """시스템 상태를 관리하고 전이 규칙을 강제한다."""

    def __init__(self):
        self._state = SystemState.INIT
        logger.info("SystemStateManager initialized | state=INIT")

    @property
    def state(self) -> SystemState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == SystemState.RUNNING

    @property
    def is_ready(self) -> bool:
        return self._state == SystemState.READY

    @property
    def is_stopped(self) -> bool:
        return self._state in (SystemState.STOPPED, SystemState.ERROR)

    def transition_to(self, new_state: SystemState):
        """
        상태를 전이한다.
        유효하지 않은 전이 시 StateTransitionError를 발생시킨다.
        """
        valid = VALID_TRANSITIONS.get(self._state, set())
        if new_state not in valid:
            raise StateTransitionError(
                f"Invalid transition: {self._state.value} → {new_state.value} "
                f"(valid: {[s.value for s in valid]})"
            )
        old = self._state
        self._state = new_state
        logger.info("State transition | %s → %s", old.value, new_state.value)

    def force_error(self, reason: str = ""):
        """어느 상태에서든 ERROR로 강제 전이한다."""
        old = self._state
        self._state = SystemState.ERROR
        logger.critical("FORCED ERROR state | %s → ERROR | reason=%s", old.value, reason)
