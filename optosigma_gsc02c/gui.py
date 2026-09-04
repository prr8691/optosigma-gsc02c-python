from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None

from .controller import GSC02C, StageConfig
from .simulated import SimulatedGSC02C


class StageControlApp(tk.Tk):
    """Simple SGSample-style desktop controller for one delay-stage axis."""

    REFRESH_MS = 250

    def __init__(self) -> None:
        super().__init__()

        self.title("OptoSigma GSC-02C Delay Stage")
        self.geometry("760x620")
        self.minsize(700, 570)

        self.stage = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.operation_running = False

        # User-editable values.
        self.mode_var = tk.StringVar(value="Simulation")
        self.port_var = tk.StringVar(value="")
        self.axis_var = tk.IntVar(value=1)
        self.position_var = tk.StringVar(value="--")
        self.connection_var = tk.StringVar(value="Disconnected")
        self.step_var = tk.StringVar(value="0.100")
        self.target_var = tk.StringVar(value="10.000")
        self.start_speed_var = tk.StringVar(value="0.500")
        self.max_speed_var = tk.StringVar(value="10.000")
        self.accel_var = tk.StringVar(value="200")
        self.home_direction_var = tk.StringVar(value="-")

        self._build_ui()
        self._set_connected_ui(False)
        self.refresh_ports()
        self.after(100, self._process_events)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        title = ttk.Label(
            outer,
            text="GSC-02C Delay Stage Control",
            font=("TkDefaultFont", 18, "bold"),
        )
        title.grid(row=0, column=0, sticky="w", pady=(0, 12))

        # Connection -----------------------------------------------------
        connection = ttk.LabelFrame(outer, text="Connection", padding=12)
        connection.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        for col in range(7):
            connection.columnconfigure(col, weight=0)
        connection.columnconfigure(3, weight=1)

        ttk.Label(connection, text="Mode").grid(row=0, column=0, sticky="w")
        mode_box = ttk.Combobox(
            connection,
            textvariable=self.mode_var,
            values=("Simulation", "Hardware"),
            state="readonly",
            width=12,
        )
        mode_box.grid(row=1, column=0, padx=(0, 10), sticky="w")
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self._mode_changed())

        ttk.Label(connection, text="Serial port").grid(row=0, column=1, sticky="w")
        self.port_box = ttk.Combobox(
            connection,
            textvariable=self.port_var,
            state="readonly",
            width=24,
        )
        self.port_box.grid(row=1, column=1, padx=(0, 6), sticky="ew")

        self.refresh_button = ttk.Button(
            connection,
            text="Refresh",
            command=self.refresh_ports,
        )
        self.refresh_button.grid(row=1, column=2, padx=(0, 12))

        ttk.Label(connection, text="Axis").grid(row=0, column=3, sticky="w")
        axis_box = ttk.Combobox(
            connection,
            textvariable=self.axis_var,
            values=(1, 2),
            state="readonly",
            width=5,
        )
        axis_box.grid(row=1, column=3, sticky="w")

        self.connect_button = ttk.Button(
            connection,
            text="Connect",
            command=self.toggle_connection,
        )
        self.connect_button.grid(row=1, column=4, padx=(12, 8))

        ttk.Label(connection, textvariable=self.connection_var).grid(
            row=1, column=5, sticky="w"
        )

        # Position display ----------------------------------------------
        position = ttk.LabelFrame(outer, text="Position", padding=12)
        position.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        position.columnconfigure(0, weight=1)

        ttk.Label(position, text="Current position").grid(row=0, column=0)
        ttk.Label(
            position,
            textvariable=self.position_var,
            font=("TkDefaultFont", 28, "bold"),
        ).grid(row=1, column=0, pady=(2, 0))
        ttk.Label(position, text="mm    (software range: 0 to 85 mm)").grid(
            row=2, column=0
        )

        # Motion controls ------------------------------------------------
        movement = ttk.LabelFrame(outer, text="Movement", padding=12)
        movement.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for col in range(5):
            movement.columnconfigure(col, weight=1)

        ttk.Label(movement, text="Step size (mm)").grid(row=0, column=0, columnspan=2)
        ttk.Entry(movement, textvariable=self.step_var, width=12).grid(
            row=1, column=0, columnspan=2, pady=(3, 8)
        )

        self.backward_button = ttk.Button(
            movement,
            text="◀  Step Back",
            command=lambda: self._relative_move(-1),
        )
        self.backward_button.grid(row=2, column=0, padx=4, sticky="ew")

        self.forward_button = ttk.Button(
            movement,
            text="Step Forward  ▶",
            command=lambda: self._relative_move(+1),
        )
        self.forward_button.grid(row=2, column=1, padx=4, sticky="ew")

        ttk.Separator(movement, orient="vertical").grid(
            row=0, column=2, rowspan=3, sticky="ns", padx=16
        )

        ttk.Label(movement, text="Absolute target (mm)").grid(
            row=0, column=3, columnspan=2
        )
        ttk.Entry(movement, textvariable=self.target_var, width=12).grid(
            row=1, column=3, columnspan=2, pady=(3, 8)
        )

        self.go_button = ttk.Button(
            movement,
            text="Move to Position",
            command=self._absolute_move,
        )
        self.go_button.grid(row=2, column=3, columnspan=2, padx=4, sticky="ew")

        # Motion settings ------------------------------------------------
        settings = ttk.LabelFrame(outer, text="Motion Settings", padding=12)
        settings.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        for col in range(7):
            settings.columnconfigure(col, weight=1)

        ttk.Label(settings, text="Start speed (mm/s)").grid(row=0, column=0)
        ttk.Entry(settings, textvariable=self.start_speed_var, width=10).grid(
            row=1, column=0, padx=4
        )

        ttk.Label(settings, text="Max speed (mm/s)").grid(row=0, column=1)
        ttk.Entry(settings, textvariable=self.max_speed_var, width=10).grid(
            row=1, column=1, padx=4
        )

        ttk.Label(settings, text="Ramp time (ms)").grid(row=0, column=2)
        ttk.Entry(settings, textvariable=self.accel_var, width=10).grid(
            row=1, column=2, padx=4
        )

        self.apply_settings_button = ttk.Button(
            settings,
            text="Apply Settings",
            command=self._apply_motion_settings,
        )
        self.apply_settings_button.grid(row=1, column=3, padx=(12, 4), sticky="ew")

        ttk.Label(settings, text="Home direction").grid(row=0, column=4)
        ttk.Combobox(
            settings,
            textvariable=self.home_direction_var,
            values=("-", "+"),
            state="readonly",
            width=5,
        ).grid(row=1, column=4)

        self.home_button = ttk.Button(settings, text="Home", command=self._home)
        self.home_button.grid(row=1, column=5, padx=4, sticky="ew")

        self.stop_button = tk.Button(
            settings,
            text="STOP",
            command=self._stop,
            font=("TkDefaultFont", 11, "bold"),
            padx=10,
            pady=4,
        )
        self.stop_button.grid(row=1, column=6, padx=(8, 0), sticky="ew")

        # Log ------------------------------------------------------------
        log_frame = ttk.LabelFrame(outer, text="Status log", padding=8)
        log_frame.grid(row=5, column=0, sticky="nsew")
        outer.rowconfigure(5, weight=1)

        self.log = tk.Text(log_frame, height=8, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)
        self._log("Start in Simulation mode to test without hardware.")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._mode_changed()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def refresh_ports(self) -> None:
        ports = [] if list_ports is None else [port.device for port in list_ports.comports()]
        self.port_box["values"] = ports
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])
        elif not ports:
            self.port_var.set("")

    def _mode_changed(self) -> None:
        hardware = self.mode_var.get() == "Hardware"
        self.port_box.configure(state="readonly" if hardware else "disabled")
        self.refresh_button.configure(state="normal" if hardware else "disabled")

    def toggle_connection(self) -> None:
        if self.stage is None:
            self._connect()
        else:
            self._disconnect()

    def _connect(self) -> None:
        mode = self.mode_var.get()
        axis = int(self.axis_var.get())

        try:
            if mode == "Simulation":
                stage = SimulatedGSC02C(axis=axis, config=StageConfig())
            else:
                port = self.port_var.get().strip()
                if not port:
                    raise ValueError(
                        "No serial port selected. Connect the controller and click Refresh."
                    )
                stage = GSC02C(port=port, axis=axis, config=StageConfig())

            stage.connect()
            self.stage = stage
            self.connection_var.set(f"Connected ({mode})")
            self.connect_button.configure(text="Disconnect")
            self._set_connected_ui(True)
            self._log(f"Connected in {mode} mode on axis {axis}.")
            self._update_position()
        except Exception as exc:
            self.stage = None
            messagebox.showerror("Connection failed", str(exc))
            self._log(f"Connection failed: {exc}")

    def _disconnect(self) -> None:
        try:
            if self.stage is not None:
                self.stage.close()
        finally:
            self.stage = None
            self.position_var.set("--")
            self.connection_var.set("Disconnected")
            self.connect_button.configure(text="Connect")
            self._set_connected_ui(False)
            self._log("Disconnected.")

    def _set_connected_ui(self, connected: bool) -> None:
        state = "normal" if connected else "disabled"
        for widget in (
            self.backward_button,
            self.forward_button,
            self.go_button,
            self.apply_settings_button,
            self.home_button,
            self.stop_button,
        ):
            widget.configure(state=state)

    # ------------------------------------------------------------------
    # Background operations
    # ------------------------------------------------------------------

    def _run_operation(self, description: str, function) -> None:
        if self.stage is None:
            messagebox.showwarning("Not connected", "Connect to a stage first.")
            return
        if self.operation_running:
            messagebox.showinfo("Stage busy", "Wait for the current operation to finish.")
            return

        self.operation_running = True
        self._log(description)

        def worker() -> None:
            try:
                function()
                position = self.stage.get_position_mm()
                self.events.put(("done", (description, position)))
            except Exception as exc:
                self.events.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _process_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "done":
                    description, position = payload
                    self.position_var.set(f"{position:.3f}")
                    self._log(f"Done: {description}  Position = {position:.3f} mm")
                    self.operation_running = False
                elif kind == "error":
                    self.operation_running = False
                    self._log(f"ERROR: {payload}")
                    messagebox.showerror("Stage command failed", str(payload))
        except queue.Empty:
            pass

        self.after(100, self._process_events)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _relative_move(self, direction: int) -> None:
        try:
            step = abs(float(self.step_var.get()))
            if step <= 0:
                raise ValueError("Step size must be greater than zero.")
        except ValueError as exc:
            messagebox.showerror("Invalid step", str(exc))
            return

        signed_step = direction * step
        self._run_operation(
            f"Relative move {signed_step:+.3f} mm",
            lambda: self.stage.move_relative_mm(signed_step),
        )

    def _absolute_move(self) -> None:
        try:
            target = float(self.target_var.get())
            if not 0 <= target <= 85:
                raise ValueError("Target must be between 0 and 85 mm.")
        except ValueError as exc:
            messagebox.showerror("Invalid target", str(exc))
            return

        self._run_operation(
            f"Absolute move to {target:.3f} mm",
            lambda: self.stage.move_absolute_mm(target),
        )

    def _apply_motion_settings(self) -> None:
        try:
            start_speed = float(self.start_speed_var.get())
            max_speed = float(self.max_speed_var.get())
            accel_ms = int(self.accel_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid settings",
                "Speed values must be numbers and ramp time must be an integer.",
            )
            return

        def apply() -> None:
            self.stage.set_max_speed_mm_s(
                max_speed_mm_s=max_speed,
                start_speed_mm_s=start_speed,
                accel_time_ms=accel_ms,
            )

        self._run_operation(
            f"Apply speed: start={start_speed:g} mm/s, max={max_speed:g} mm/s, "
            f"ramp={accel_ms} ms",
            apply,
        )

    def _home(self) -> None:
        direction = self.home_direction_var.get()

        if self.mode_var.get() == "Hardware":
            confirmed = messagebox.askyesno(
                "Confirm homing",
                "Homing moves the physical stage toward an origin/limit.\n\n"
                f"Home in direction {direction}?",
            )
            if not confirmed:
                return

        self._run_operation(
            f"Home in {direction} direction",
            lambda: self.stage.home(direction),
        )

    def _stop(self) -> None:
        if self.stage is None:
            return
        try:
            self.stage.stop()
            self.operation_running = False
            self._log("STOP command sent.")
            self._update_position()
        except Exception as exc:
            self._log(f"STOP failed: {exc}")
            messagebox.showerror("Stop failed", str(exc))

    def _update_position(self) -> None:
        if self.stage is None:
            return
        try:
            self.position_var.set(f"{self.stage.get_position_mm():.3f}")
        except Exception as exc:
            self._log(f"Could not read position: {exc}")

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_close(self) -> None:
        if self.stage is not None:
            try:
                self.stage.close()
            except Exception:
                pass
        self.destroy()


def main() -> None:
    app = StageControlApp()
    app.mainloop()


if __name__ == "__main__":
    main()
