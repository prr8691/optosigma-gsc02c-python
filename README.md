# OptoSigma GSC-02C Python Delay-Stage Controller

Python control software for an OptoSigma / Sigma Koki **GSC-02C** controller with an **OSMS20-85** motorized stage.

The project now contains both:

- a hardware driver using RS-232 through `pyserial`, and
- an SGSample-style desktop GUI with a **Simulation** mode that is safe to run without a controller connected.

## What the GUI can do

- connect in **Simulation** or **Hardware** mode
- select axis 1 or 2
- detect available serial ports on Windows
- display current position in mm
- step forward / backward by a chosen distance
- move to an absolute position
- set starting speed, maximum speed, and acceleration/deceleration ramp time
- home in the + or - direction
- send a controlled stop command
- enforce the software travel range **0 to 85 mm**
- show a status/event log

## Project environment: Astral `uv`

Do **not** copy the `.venv` directory from one computer to another. Virtual environments contain OS-specific paths and executables.

Instead, transfer/clone this repository including `pyproject.toml`, `.python-version`, and `uv.lock`. On each computer, `uv sync` recreates the correct local `.venv` from the lockfile.

### Install uv on macOS/Linux

See Astral's official installer documentation. One supported command is:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install uv on Windows

In PowerShell, Astral documents:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

or with WinGet:

```powershell
winget install --id=astral-sh.uv -e
```

Close and reopen PowerShell after installation if `uv` is not immediately found.

## First-time setup

From the repository folder:

```bash
uv sync
```

`uv` will create/manage the project environment in `.venv` and install the package dependencies.

## Run the GUI without hardware

From the repository folder:

```bash
uv run gsc02c-ui
```

The program starts in **Simulation** mode.

1. Leave Mode = `Simulation`.
2. Click **Connect**.
3. Try a 0.100 mm forward/backward step.
4. Try an absolute move.
5. Confirm attempts outside 0 to 85 mm are rejected.

No serial port is opened in Simulation mode.

## Run on the Windows lab computer with the real controller

1. Clone/download this same repository onto the Windows PC.
2. Install `uv`.
3. In PowerShell, change into the repository folder.
4. Run:

```powershell
uv sync
uv run gsc02c-ui
```

5. First test the GUI in **Simulation** mode.
6. Connect the GSC-02C to the Windows PC.
7. Change Mode to **Hardware**.
8. Click **Refresh** and select the controller's COM port (for example `COM3`).
9. Choose the correct axis.
10. Click **Connect**.

For the first real-stage test, keep the optics clear and use a very small step such as **0.010 mm**.

## Run simulator tests

```bash
uv run python -m unittest discover -s tests -v
```

These tests exercise movement and the 85 mm software limit without touching hardware.

## Main source files

```text
optosigma_gsc02c/
    controller.py   # Real GSC-02C serial driver
    simulated.py    # Safe software-only fake stage
    gui.py          # Desktop GUI
    __init__.py

tests/
    test_simulated.py
```

## Important hardware note

The GSC-02C is an open-loop stepper controller. The software-reported coordinate is based on commanded pulses, not independent encoder feedback. Verify the physical origin, homing direction, limit switches, axis configuration, and stage resolution on the real setup before relying on absolute coordinates.
