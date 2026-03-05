"""Tests for ios_gps_spoofer.simulation.state_machine module.

Tests cover:
- Initial state is IDLE
- All valid transitions
- Invalid transitions raise SimulationStateError
- State properties (is_running, is_paused, is_stopped, is_idle, is_active)
- wait_for_resume behavior (blocks on pause, unblocks on resume/stop)
- get_valid_actions
- Thread safety of transitions
"""

import threading
import time

import pytest

from ios_gps_spoofer.simulation.exceptions import SimulationStateError
from ios_gps_spoofer.simulation.state_machine import (
    SimulationState,
    SimulationStateMachine,
)


class TestInitialState:
    """Tests for initial state machine state."""

    def test_initial_state_is_idle(self) -> None:
        sm = SimulationStateMachine()
        assert sm.state == SimulationState.IDLE

    def test_is_idle_true(self) -> None:
        sm = SimulationStateMachine()
        assert sm.is_idle is True

    def test_is_running_false(self) -> None:
        sm = SimulationStateMachine()
        assert sm.is_running is False

    def test_is_active_false(self) -> None:
        sm = SimulationStateMachine()
        assert sm.is_active is False


class TestValidTransitions:
    """Tests for valid state transitions."""

    def test_idle_to_running(self) -> None:
        sm = SimulationStateMachine()
        new_state = sm.transition("start")
        assert new_state == SimulationState.RUNNING
        assert sm.is_running is True

    def test_running_to_paused(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        new_state = sm.transition("pause")
        assert new_state == SimulationState.PAUSED
        assert sm.is_paused is True

    def test_paused_to_running(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("pause")
        new_state = sm.transition("resume")
        assert new_state == SimulationState.RUNNING
        assert sm.is_running is True

    def test_running_to_stopped(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        new_state = sm.transition("stop")
        assert new_state == SimulationState.STOPPED
        assert sm.is_stopped is True

    def test_paused_to_stopped(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("pause")
        new_state = sm.transition("stop")
        assert new_state == SimulationState.STOPPED
        assert sm.is_stopped is True

    def test_full_lifecycle_start_pause_resume_stop(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("pause")
        sm.transition("resume")
        sm.transition("stop")
        assert sm.state == SimulationState.STOPPED


class TestInvalidTransitions:
    """Tests for invalid state transitions."""

    def test_idle_cannot_pause(self) -> None:
        sm = SimulationStateMachine()
        with pytest.raises(SimulationStateError, match="idle"):
            sm.transition("pause")

    def test_idle_cannot_resume(self) -> None:
        sm = SimulationStateMachine()
        with pytest.raises(SimulationStateError, match="idle"):
            sm.transition("resume")

    def test_idle_cannot_stop(self) -> None:
        sm = SimulationStateMachine()
        with pytest.raises(SimulationStateError, match="idle"):
            sm.transition("stop")

    def test_running_cannot_start(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        with pytest.raises(SimulationStateError, match="running"):
            sm.transition("start")

    def test_running_cannot_resume(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        with pytest.raises(SimulationStateError, match="running"):
            sm.transition("resume")

    def test_paused_cannot_start(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("pause")
        with pytest.raises(SimulationStateError, match="paused"):
            sm.transition("start")

    def test_paused_cannot_pause(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("pause")
        with pytest.raises(SimulationStateError, match="paused"):
            sm.transition("pause")

    def test_stopped_is_terminal(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("stop")
        with pytest.raises(SimulationStateError, match="stopped"):
            sm.transition("start")

    def test_stopped_cannot_pause(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("stop")
        with pytest.raises(SimulationStateError, match="stopped"):
            sm.transition("pause")

    def test_unknown_action_raises(self) -> None:
        sm = SimulationStateMachine()
        with pytest.raises(SimulationStateError):
            sm.transition("fly")


class TestStateProperties:
    """Tests for is_* properties."""

    def test_is_active_when_running(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        assert sm.is_active is True

    def test_is_active_when_paused(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("pause")
        assert sm.is_active is True

    def test_is_active_false_when_stopped(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("stop")
        assert sm.is_active is False


class TestWaitForResume:
    """Tests for wait_for_resume blocking behavior."""

    def test_returns_immediately_when_running(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        # Should not block
        assert sm.wait_for_resume(timeout=0.1) is True

    def test_blocks_when_paused(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("pause")

        # Should block and timeout
        start = time.monotonic()
        result = sm.wait_for_resume(timeout=0.2)
        elapsed = time.monotonic() - start
        assert result is False
        assert elapsed >= 0.15  # account for timing imprecision

    def test_unblocks_on_resume(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("pause")

        unblocked = threading.Event()

        def waiter() -> None:
            sm.wait_for_resume(timeout=5.0)
            unblocked.set()

        thread = threading.Thread(target=waiter)
        thread.start()

        # Give thread time to start waiting
        time.sleep(0.1)

        sm.transition("resume")
        assert unblocked.wait(timeout=2.0), "Thread was not unblocked by resume"
        thread.join(timeout=1.0)

    def test_unblocks_on_stop(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("pause")

        unblocked = threading.Event()

        def waiter() -> None:
            sm.wait_for_resume(timeout=5.0)
            unblocked.set()

        thread = threading.Thread(target=waiter)
        thread.start()

        time.sleep(0.1)
        sm.transition("stop")
        assert unblocked.wait(timeout=2.0), "Thread was not unblocked by stop"
        thread.join(timeout=1.0)


class TestGetValidActions:
    """Tests for get_valid_actions."""

    def test_idle_actions(self) -> None:
        sm = SimulationStateMachine()
        assert sm.get_valid_actions() == ["start"]

    def test_running_actions(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        actions = sm.get_valid_actions()
        assert "pause" in actions
        assert "stop" in actions

    def test_paused_actions(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("pause")
        actions = sm.get_valid_actions()
        assert "resume" in actions
        assert "stop" in actions

    def test_stopped_no_actions(self) -> None:
        sm = SimulationStateMachine()
        sm.transition("start")
        sm.transition("stop")
        assert sm.get_valid_actions() == []


class TestThreadSafety:
    """Thread safety of state transitions."""

    def test_concurrent_transitions_no_crash(self) -> None:
        """Multiple threads performing transitions should not corrupt state."""
        errors: list[Exception] = []

        def run_lifecycle() -> None:
            try:
                sm = SimulationStateMachine()
                sm.transition("start")
                sm.transition("pause")
                sm.transition("resume")
                sm.transition("stop")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=run_lifecycle) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(errors) == 0, f"Errors: {errors}"
