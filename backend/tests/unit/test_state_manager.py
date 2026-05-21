"""
core/state_manager.py 단위 테스트
TC-STA-001 ~ TC-STA-006: 상태 전이 규칙 검증 (SAD §5.1)
"""

import pytest
from common.enums import SystemState
from common.exceptions import StateTransitionError
from core.state_manager import SystemStateManager


class TestSystemStateManager:

    def test_initial_state_is_init(self):
        """TC-STA-001: 초기 상태는 INIT이다."""
        sm = SystemStateManager()
        assert sm.state == SystemState.INIT

    def test_valid_transition_init_to_ready(self):
        """TC-STA-002: INIT → READY 전이."""
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        assert sm.state == SystemState.READY
        assert sm.is_ready is True

    def test_valid_transition_ready_to_running(self):
        """TC-STA-003: READY → RUNNING 전이."""
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        sm.transition_to(SystemState.RUNNING)
        assert sm.state == SystemState.RUNNING
        assert sm.is_running is True

    def test_full_lifecycle(self):
        """TC-STA-004: 전체 생명주기 (INIT→READY→RUNNING→STOPPING→STOPPED)."""
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        sm.transition_to(SystemState.RUNNING)
        sm.transition_to(SystemState.STOPPING)
        sm.transition_to(SystemState.STOPPED)
        assert sm.state == SystemState.STOPPED
        assert sm.is_stopped is True

    def test_invalid_transition_raises_error(self):
        """TC-STA-005: 잘못된 전이 시 StateTransitionError 발생."""
        sm = SystemStateManager()
        # INIT → RUNNING (READY를 건너뜀)
        with pytest.raises(StateTransitionError):
            sm.transition_to(SystemState.RUNNING)

    def test_invalid_transition_running_to_ready(self):
        """RUNNING → READY는 불가."""
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        sm.transition_to(SystemState.RUNNING)
        with pytest.raises(StateTransitionError):
            sm.transition_to(SystemState.READY)

    def test_force_error_from_any_state(self):
        """TC-STA-006: 어느 상태에서든 ERROR로 강제 전이 가능."""
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        sm.transition_to(SystemState.RUNNING)
        sm.force_error("Critical failure")
        assert sm.state == SystemState.ERROR

    def test_error_recovery_to_ready(self):
        """ERROR → READY 복구."""
        sm = SystemStateManager()
        sm.force_error("test")
        sm.transition_to(SystemState.READY)
        assert sm.state == SystemState.READY

    def test_stopped_to_init_restart(self):
        """STOPPED → INIT 재기동."""
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        sm.transition_to(SystemState.RUNNING)
        sm.transition_to(SystemState.STOPPING)
        sm.transition_to(SystemState.STOPPED)
        sm.transition_to(SystemState.INIT)
        assert sm.state == SystemState.INIT
