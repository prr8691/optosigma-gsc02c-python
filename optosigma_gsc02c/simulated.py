from __future__ import annotations

import time
from dataclasses import dataclass

from .controller import StageConfig


@dataclass
class SimulatedMotion:
    """Stores the user-facing motion settings used by the simulator."""

    start_speed_mm_s: float = 0.5
    max_speed_mm_s: float = 10.0
    accel_time_ms: int = 200


class SimulatedGSC02C:
    """Software-only stand-in for a GSC-02C + OSMS20-85.

    This class intentionally implements the same high-level methods used by the
    GUI as :class:`GSC02C`, but it never opens a serial port and never talks to
    hardware.  It is therefore safe for UI development on a laptop that is not
    connected to the delay stage.
    """

    def __init__(
        self,
        axis: int = 1,
        config: StageConfig = StageConfig(),
        initial_position_mm: float = 42.5,
    ):
        if axis not in (1, 2):
            raise ValueError("axis must be 1 or 2")

        self.axis = axis
        self.config = config
        self.motion = SimulatedMotion()
        self._position_mm = float(initial_position_mm)
        self._connected = False
        self._busy = False
        self._stopped = False
        self._check_position(self._position_mm)

    def connect(self) -> None:
        """Pretend to connect to a controller."""
        self._connected = True

    def close(self) -> None:
        """Pretend to close the controller connection."""
        self._connected = False
        self._busy = False

    def _require_connection(self) -> None:
        if not self._connected:
            raise RuntimeError("Simulated controller is not connected.")

    def _check_position(self, position_mm: float) -> None:
        if not (
            self.config.min_position_mm
            <= position_mm
            <= self.config.max_position_mm
        ):
            raise ValueError(
                f"Requested position {position_mm:.3f} mm is outside "
                f"the {self.config.min_position_mm:.1f} to "
                f"{self.config.max_position_mm:.1f} mm software limits."
            )

    def get_position_mm(self) -> float:
        self._require_connection()
        return self._position_mm

    def is_busy(self) -> bool:
        self._require_connection()
        return self._busy

    def set_max_speed_mm_s(
        self,
        max_speed_mm_s: float,
        start_speed_mm_s: float = 0.5,
        accel_time_ms: int = 200,
    ) -> None:
        self._require_connection()

        if max_speed_mm_s <= 0:
            raise ValueError("Maximum speed must be greater than zero.")
        if start_speed_mm_s <= 0:
            raise ValueError("Starting speed must be greater than zero.")
        if start_speed_mm_s > max_speed_mm_s:
            raise ValueError("Starting speed cannot exceed maximum speed.")
        if not 0 <= accel_time_ms <= 1000:
            raise ValueError("Acceleration time must be between 0 and 1000 ms.")

        self.motion = SimulatedMotion(
            start_speed_mm_s=float(start_speed_mm_s),
            max_speed_mm_s=float(max_speed_mm_s),
            accel_time_ms=int(accel_time_ms),
        )

    def _simulate_move(self, target_mm: float) -> None:
        self._require_connection()
        self._check_position(target_mm)

        distance_mm = abs(target_mm - self._position_mm)
        self._busy = True
        self._stopped = False

        # Keep simulation responsive: imitate motion time, but cap the delay so
        # a large 85 mm move does not make UI testing painfully slow.
        speed = max(self.motion.max_speed_mm_s, 0.001)
        simulated_seconds = min(distance_mm / speed, 0.35)
        time.sleep(simulated_seconds)

        if not self._stopped:
            self._position_mm = target_mm

        self._busy = False

    def move_relative_mm(self, distance_mm: float, wait: bool = True) -> None:
        del wait  # The GUI runs moves in a worker thread either way.
        self._simulate_move(self._position_mm + float(distance_mm))

    def move_absolute_mm(self, position_mm: float, wait: bool = True) -> None:
        del wait
        self._simulate_move(float(position_mm))

    def step_forward(self, step_mm: float, wait: bool = True) -> None:
        self.move_relative_mm(abs(float(step_mm)), wait=wait)

    def step_backward(self, step_mm: float, wait: bool = True) -> None:
        self.move_relative_mm(-abs(float(step_mm)), wait=wait)

    def home(self, direction: str = "-", wait: bool = True) -> None:
        del wait
        if direction not in ("+", "-"):
            raise ValueError("direction must be '+' or '-'")

        target = (
            self.config.min_position_mm
            if direction == "-"
            else self.config.max_position_mm
        )
        self._simulate_move(target)

    def stop(self) -> None:
        self._require_connection()
        self._stopped = True
        self._busy = False
