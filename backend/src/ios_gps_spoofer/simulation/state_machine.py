"""Simulation state machine: IDLE -> RUNNING -> PAUSED -> STOPPED.

Enforces valid state transitions and provides thread-safe state queries.
The state machine is a separate class from the simulator so it can be
tested independently and its transition rules are clearly defined.

State Diagram
-------------
::

    IDLE ──start──> RUNNING ──pause──> PAUSED
                      │  ^               │
                      │  └───resume──────┘
                      │
                      ├──stop──> STOPPED
                      │
    PAUSED ──stop──> STOPPED

    STOPPED is a terminal state.  To restart, create a new state machine.

Thread Safety
-------------
All state reads and transitions are protected by a threading lock.
The ``wait_for_resume()`` method uses a ``threading.Event`` so the
simulation thread can efficiently block while paused without busy-waiting.
"""

from __future__ import annotations

import enum
import logging
import threading

from ios_gps_spoofer.simulation.exceptions import SimulationStateError

logger = logging.getLogger(__name__)


class SimulationState(enum.Enum):
    """Possible states of a path simulation."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


# Valid transitions: {current_state: {action: next_state}}
_TRANSITIONS: dict[SimulationState, dict[str, SimulationState]] = {
    SimulationState.IDLE: {
        "start": SimulationState.RUNNING,
    },
    SimulationState.RUNNING: {
        "pause": SimulationState.PAUSED,
        "stop": SimulationState.STOPPED,
    },
    SimulationState.PAUSED: {
        "resume": SimulationState.RUNNING,
        "stop": SimulationState.STOPPED,
    },
    SimulationState.STOPPED: {},  # terminal state, no transitions
}


class SimulationStateMachine:
    """Thread-safe state machine for path simulation lifecycle.

    Usage::

        sm = SimulationStateMachine()
        sm.transition("start")   # IDLE -> RUNNING
        sm.transition("pause")   # RUNNING -> PAUSED
        sm.transition("resume")  # PAUSED -> RUNNING
        sm.transition("stop")    # RUNNING -> STOPPED
    """

    def __init__(self) -> None:
        """Initialize in the IDLE state."""
        self._state = SimulationState.IDLE
        self._lock = threading.Lock()

        # Event used to signal the simulation thread when resuming
        # from PAUSED state.  Set when RUNNING, cleared when PAUSED.
        self._resume_event = threading.Event()
        self._resume_event.set()  # initially set (not paused)

    @property
    def state(self) -> SimulationState:
        """Current simulation state (thread-safe read)."""
        with self._lock:
            return self._state

    @property
    def is_running(self) -> bool:
        """True if the simulation is currently running."""
        with self._lock:
            return self._state == SimulationState.RUNNING

    @property
    def is_paused(self) -> bool:
        """True if the simulation is currently paused."""
        with self._lock:
            return self._state == SimulationState.PAUSED

    @property
    def is_stopped(self) -> bool:
        """True if the simulation has been stopped (terminal state)."""
        with self._lock:
            return self._state == SimulationState.STOPPED

    @property
    def is_idle(self) -> bool:
        """True if the simulation has not started yet."""
        with self._lock:
            return self._state == SimulationState.IDLE

    @property
    def is_active(self) -> bool:
        """True if the simulation is running or paused (not idle or stopped)."""
        with self._lock:
            return self._state in (
                SimulationState.RUNNING,
                SimulationState.PAUSED,
            )

    def transition(self, action: str) -> SimulationState:
        """Attempt a state transition.

        Args:
            action: The transition action (``"start"``, ``"pause"``,
                ``"resume"``, ``"stop"``).

        Returns:
            The new state after the transition.

        Raises:
            SimulationStateError: If the transition is not valid for
                the current state.
        """
        with self._lock:
            current = self._state
            allowed = _TRANSITIONS.get(current, {})

            if action not in allowed:
                raise SimulationStateError(current.value, action)

            new_state = allowed[action]
            self._state = new_state

            # Manage the resume event
            if new_state == SimulationState.PAUSED:
                self._resume_event.clear()
            elif new_state == SimulationState.RUNNING:
                self._resume_event.set()
            elif new_state == SimulationState.STOPPED:
                # Unblock any thread waiting on resume so it can exit
                self._resume_event.set()

            logger.info(
                "Simulation state: %s -[%s]-> %s",
                current.value,
                action,
                new_state.value,
            )
            return new_state

    def wait_for_resume(self, timeout: float | None = None) -> bool:
        """Block until the simulation is no longer paused.

        This should be called by the simulation thread at each iteration.
        When the state is RUNNING, this returns immediately.  When PAUSED,
        it blocks until ``resume`` or ``stop`` is called.

        Args:
            timeout: Maximum seconds to wait.  None means wait forever.

        Returns:
            True if the event was set (resume or stop occurred).
            False if the timeout expired while still paused.
        """
        return self._resume_event.wait(timeout=timeout)

    def get_valid_actions(self) -> list[str]:
        """Return the list of valid actions for the current state.

        Returns:
            List of action strings that can be passed to ``transition()``.
        """
        with self._lock:
            return list(_TRANSITIONS.get(self._state, {}).keys())
