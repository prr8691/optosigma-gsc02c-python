from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

try:
    import serial
except ImportError:  # Simulation mode can still run before pyserial is installed.
    serial = None


class GSC02CError(RuntimeError):
    """
    Custom error for problems communicating with the GSC-02C.

    Using our own error type makes it easier to distinguish controller
    communication problems from normal Python errors such as ValueError.
    """


@dataclass(frozen=True)
class StageConfig:
    """
    Physical settings for the motorized stage attached to the controller.

    For an OSMS20-85 in half-step mode:
        1 pulse = 1 micrometer
        travel range = approximately 0 to 85 mm

    If your controller/stage is configured differently, change these values.
    """

    # Physical distance moved by one controller pulse.
    um_per_pulse: float = 1.0

    # Software limits. These prevent us from intentionally commanding the
    # stage outside the allowed travel range.
    min_position_mm: float = 0.0
    max_position_mm: float = 85.0


class GSC02C:
    """
    Python driver for the OptoSigma / Sigma Koki GSC-02C controller.

    Communication chain:

        Python
          |
        pyserial
          |
        RS-232
          |
        GSC-02C controller
          |
        OSMS20-85 motorized stage

    The controller uses ASCII text commands such as:

        Q:      -> ask for position/status
        M:      -> prepare a relative movement
        A:      -> prepare an absolute movement
        G:      -> execute prepared movement
        D:      -> set speed and acceleration/deceleration
        H:      -> home / mechanical origin return
        L:      -> stop
        !:      -> ask whether controller is busy

    Parameters
    ----------
    port:
        Serial port name.

        Windows examples:
            "COM3"
            "COM7"

        Linux examples:
            "/dev/ttyUSB0"
            "/dev/ttyS0"

    axis:
        GSC-02C can control two axes. Use 1 or 2.

    baudrate:
        Communication speed. The OptoSigma sample uses 9600 baud.

    timeout:
        Maximum time to wait for a reply from the controller.

    config:
        Physical stage settings and software travel limits.
    """

    # The controller expects each command to end with carriage-return + line-feed.
    TERMINATOR = "\r\n"

    def __init__(
        self,
        port: str,
        axis: int = 1,
        baudrate: int = 9600,
        timeout: float = 2.0,
        config: StageConfig = StageConfig(),
    ):
        # GSC-02C only has axes 1 and 2.
        if axis not in (1, 2):
            raise ValueError("axis must be 1 or 2")

        # Save connection/configuration information.
        self.port = port
        self.axis = axis
        self.baudrate = baudrate
        self.timeout = timeout
        self.config = config

        # This will hold the pyserial connection after connect() is called.
        self.ser: Optional[Any] = None

    # ------------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Open the RS-232 serial connection to the controller.
        """

        # If already connected, do nothing.
        if self.ser is not None and self.ser.is_open:
            return

        if serial is None:
            raise GSC02CError(
                "pyserial is required for Hardware mode. Run `uv sync` first."
            )

        # These serial settings match the OptoSigma sample program:
        # 9600 baud, 8 data bits, no parity, 1 stop bit, RTS/CTS handshaking.
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            rtscts=True,
        )

    def close(self) -> None:
        """
        Close the serial port safely.
        """
        if self.ser is not None and self.ser.is_open:
            self.ser.close()

    def __enter__(self) -> "GSC02C":
        """
        Allows convenient usage like:

            with GSC02C("COM7") as stage:
                stage.move_relative_mm(1)

        The serial connection automatically opens.
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """
        Automatically close the serial connection when leaving a with-block.
        """
        self.close()

    def _require_connection(self) -> Any:
        """
        Internal helper that makes sure the controller is connected.

        Methods beginning with an underscore are intended to be internal
        implementation details rather than the main public API.
        """
        if self.ser is None or not self.ser.is_open:
            raise GSC02CError("Controller is not connected.")

        return self.ser

    def _write(self, command: str) -> None:
        """
        Send one ASCII command to the GSC-02C.

        Example:
            self._write("G:")

        actually sends:
            G:\r\n
        """

        ser = self._require_connection()

        # Add the controller's required line ending.
        full_command = command + self.TERMINATOR

        # Serial ports transmit bytes, so convert the Python string to ASCII.
        ser.write(full_command.encode("ascii"))

    def _query(self, command: str) -> str:
        """
        Send a command and wait for one line of response.
        """

        ser = self._require_connection()

        # Remove old unread data so we do not accidentally interpret an
        # earlier response as the response to the new command.
        ser.reset_input_buffer()

        # Send the command.
        self._write(command)

        # Read one reply line from the controller.
        reply = ser.readline().decode("ascii", errors="replace").strip()

        # An empty reply usually means timeout, unplugged cable, wrong COM port,
        # or incorrect serial communication settings.
        if not reply:
            raise GSC02CError(f"No reply to command {command!r}")

        return reply

    # ------------------------------------------------------------------
    # UNIT CONVERSION
    # ------------------------------------------------------------------

    def mm_to_pulses(self, distance_mm: float) -> int:
        """
        Convert millimeters into controller pulses.

        Default OSMS20-85 half-step configuration:

            1 pulse = 1 um
            1000 pulses = 1 mm
        """

        # Convert micrometers/pulse into millimeters/pulse.
        pulse_mm = self.config.um_per_pulse / 1000.0

        # Controller commands require an integer number of pulses.
        return int(round(distance_mm / pulse_mm))

    def pulses_to_mm(self, pulses: int) -> float:
        """
        Convert controller pulses back into millimeters.
        """
        return pulses * self.config.um_per_pulse / 1000.0

    def _check_position(self, position_mm: float) -> None:
        """
        Check whether a requested position is inside our software travel limits.

        This is an extra software safety layer. The physical limit switches are
        still important and should remain enabled/functional.
        """

        if not (
            self.config.min_position_mm
            <= position_mm
            <= self.config.max_position_mm
        ):
            raise ValueError(
                f"Requested position {position_mm:.6f} mm is outside "
                f"software limits "
                f"[{self.config.min_position_mm}, "
                f"{self.config.max_position_mm}] mm."
            )

    # ------------------------------------------------------------------
    # STATUS AND POSITION
    # ------------------------------------------------------------------

    def raw_status(self) -> str:
        """
        Return the controller's raw Q: response.

        Useful when debugging communication.
        """
        return self._query("Q:")

    def is_busy(self) -> bool:
        """
        Ask whether the controller is currently moving.

        The controller's !: command returns a response beginning with:
            B = busy
            R = ready
        """
        reply = self._query("!:")
        return reply.startswith("B")

    def wait_until_idle(
        self,
        timeout: float = 60.0,
        poll_interval: float = 0.05,
    ) -> None:
        """
        Wait until the controller reports that motion has finished.

        poll_interval = how often we ask the controller whether it is busy.
        """

        # Use monotonic time because it cannot jump due to computer clock changes.
        deadline = time.monotonic() + timeout

        while self.is_busy():

            # Protect against getting stuck forever if the stage/controller fails.
            if time.monotonic() > deadline:
                raise TimeoutError(
                    "Stage did not become ready before timeout."
                )

            time.sleep(poll_interval)

    def get_position_pulses(self) -> int:
        """
        Read the current controller coordinate in raw pulses.

        IMPORTANT:
        The GSC-02C is open-loop, so this is the controller's calculated
        position based on pulses commanded to the motor. It is not an
        independent encoder measurement of the physical carriage position.
        """

        # Ask the controller for its position/status string.
        reply = self.raw_status()

        # Q: responses contain comma-separated fields.
        fields = [field.strip() for field in reply.split(",")]

        # We need at least the two axis-coordinate fields.
        if len(fields) < 2:
            raise GSC02CError(
                f"Unexpected Q: reply: {reply!r}"
            )

        try:
            # axis=1 -> fields[0]
            # axis=2 -> fields[1]
            return int(fields[self.axis - 1])

        except ValueError as exc:
            raise GSC02CError(
                f"Could not parse position from Q: reply: {reply!r}"
            ) from exc

    def get_position_mm(self) -> float:
        """
        Read the current controller coordinate and return it in millimeters.
        """

        pulses = self.get_position_pulses()
        return self.pulses_to_mm(pulses)

    # ------------------------------------------------------------------
    # SPEED / ACCELERATION SETTINGS
    # ------------------------------------------------------------------

    def set_motion(
        self,
        start_speed_pps: int,
        max_speed_pps: int,
        accel_time_ms: int,
    ) -> None:
        """
        Set motion speed and acceleration/deceleration ramp.

        GSC-02C uses:

            S = starting speed, pulses/second
            F = maximum speed, pulses/second
            R = acceleration/deceleration time, milliseconds

        Example command:

            D:1S500F10000R200

        means axis 1:
            start at 500 pulses/s
            reach max 10000 pulses/s
            ramp over 200 ms
        """

        # Validate against controller ranges before sending anything.
        if not (1 <= start_speed_pps <= 30000):
            raise ValueError(
                "start_speed_pps must be in 1..30000"
            )

        if not (1 <= max_speed_pps <= 30000):
            raise ValueError(
                "max_speed_pps must be in 1..30000"
            )

        if max_speed_pps < start_speed_pps:
            raise ValueError(
                "max_speed_pps must be >= start_speed_pps"
            )

        if not (0 <= accel_time_ms <= 1000):
            raise ValueError(
                "accel_time_ms must be in 0..1000"
            )

        # Do not change motion settings while the stage is already moving.
        self.wait_until_idle()

        # Construct the GSC-02C D: command.
        command = (
            f"D:{self.axis}"
            f"S{start_speed_pps}"
            f"F{max_speed_pps}"
            f"R{accel_time_ms}"
        )

        self._write(command)

    def set_max_speed_mm_s(
        self,
        max_speed_mm_s: float,
        start_speed_mm_s: float = 0.5,
        accel_time_ms: int = 200,
    ) -> None:
        """
        User-friendly version of set_motion().

        Instead of thinking in pulses/second, this method lets you specify
        speeds directly in millimeters/second.
        """

        # Distance represented by one pulse, in mm.
        pulse_mm = self.config.um_per_pulse / 1000.0

        # Convert mm/s into pulses/s.
        start_pps = max(
            1,
            round(start_speed_mm_s / pulse_mm),
        )

        max_pps = max(
            1,
            round(max_speed_mm_s / pulse_mm),
        )

        self.set_motion(
            start_pps,
            max_pps,
            accel_time_ms,
        )

    # ------------------------------------------------------------------
    # MOVEMENT
    # ------------------------------------------------------------------

    @staticmethod
    def _signed_pulse_field(pulses: int) -> str:
        """
        Convert a signed integer into the format expected by the controller.

        Example:
            1000  -> "+P1000"
            -500  -> "-P500"
        """

        direction = "+" if pulses >= 0 else "-"
        return f"{direction}P{abs(pulses)}"

    def move_relative_pulses(
        self,
        pulses: int,
        wait: bool = True,
    ) -> None:
        """
        Move by a relative number of pulses.

        Positive = forward.
        Negative = backward.
        """

        # No reason to command a zero-distance movement.
        if pulses == 0:
            return

        # Wait until any previous movement is finished.
        self.wait_until_idle()

        # Calculate where this relative movement would place us.
        current_mm = self.get_position_mm()
        movement_mm = self.pulses_to_mm(pulses)
        target_mm = current_mm + movement_mm

        # Refuse commands outside the configured travel range.
        self._check_position(target_mm)

        # M: defines the relative movement.
        #
        # Example:
        #     M:1+P1000
        #
        # prepares axis 1 to move +1000 pulses.
        self._write(
            f"M:{self.axis}{self._signed_pulse_field(pulses)}"
        )

        # G: actually starts the prepared motion.
        self._write("G:")

        # Most experiment scripts are easier to write if the function does
        # not return until motion is complete.
        if wait:
            self.wait_until_idle()

    def move_relative_mm(
        self,
        distance_mm: float,
        wait: bool = True,
    ) -> None:
        """
        Move relative to the current position using millimeters.

        Examples:
            +1.0 -> move forward 1 mm
            -0.1 -> move backward 0.1 mm
        """

        pulses = self.mm_to_pulses(distance_mm)
        self.move_relative_pulses(pulses, wait=wait)

    def step_forward(
        self,
        step_mm: float,
        wait: bool = True,
    ) -> None:
        """
        Move one positive step.

        This is intended to feel like the Forward button in SG Sample.

        Example:
            stage.step_forward(0.1)

        moves +0.1 mm.
        """
        self.move_relative_mm(
            abs(step_mm),
            wait=wait,
        )

    def step_backward(
        self,
        step_mm: float,
        wait: bool = True,
    ) -> None:
        """
        Move one negative step.

        Example:
            stage.step_backward(0.1)

        moves -0.1 mm.
        """
        self.move_relative_mm(
            -abs(step_mm),
            wait=wait,
        )

    def move_absolute_pulses(
        self,
        pulses: int,
        wait: bool = True,
    ) -> None:
        """
        Move to an absolute controller coordinate in pulses.

        Unlike a relative move, the requested number here represents the
        destination coordinate rather than the movement distance.
        """

        # Convert destination to mm so software limits are easy to check.
        target_mm = self.pulses_to_mm(pulses)
        self._check_position(target_mm)

        self.wait_until_idle()

        # A: defines an absolute-position movement.
        #
        # Example:
        #     A:1+P10000
        #
        # means axis 1 destination coordinate = +10000 pulses.
        self._write(
            f"A:{self.axis}{self._signed_pulse_field(pulses)}"
        )

        # Start the movement.
        self._write("G:")

        if wait:
            self.wait_until_idle()

    def move_absolute_mm(
        self,
        position_mm: float,
        wait: bool = True,
    ) -> None:
        """
        Move to an absolute position in millimeters.

        Example:
            stage.move_absolute_mm(10)

        commands the stage/controller coordinate to 10 mm.
        """

        self._check_position(position_mm)

        pulses = self.mm_to_pulses(position_mm)

        self.move_absolute_pulses(
            pulses,
            wait=wait,
        )

    # ------------------------------------------------------------------
    # HOMING AND STOPPING
    # ------------------------------------------------------------------

    def home(
        self,
        direction: str = "-",
        wait: bool = True,
    ) -> None:
        """
        Run the controller's mechanical-origin / home operation.

        direction:
            "-" = search toward negative direction
            "+" = search toward positive direction

        You should verify which direction is physically correct for your setup
        before using this near optics or other hardware.
        """

        if direction not in ("+", "-"):
            raise ValueError(
                "direction must be '+' or '-'"
            )

        self.wait_until_idle()

        # H: starts the controller's home/origin search.
        self._write(
            f"H:{self.axis}{direction}"
        )

        # Homing can take longer than an ordinary small move.
        if wait:
            self.wait_until_idle(timeout=120.0)

    def stop(self) -> None:
        """
        Request a controlled deceleration stop.

        L: is preferable to simply killing the Python process because the
        controller can stop the motor in a controlled way.
        """
        self._write(f"L:{self.axis}")
