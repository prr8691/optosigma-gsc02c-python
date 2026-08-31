# OptoSigma GSC-02C Python Driver

Beginner-friendly Python driver for controlling an OptoSigma / Sigma Koki
GSC-02C stage controller.

The code is heavily commented so that it can also be used to learn how the
controller communication works.

## Hardware assumed

- Controller: GSC-02C
- Stage: OSMS20-85
- Communication: RS-232
- Default resolution used in this package: 1 um/pulse
- Default software travel range: 0 to 85 mm

## Install

```bash
python -m pip install pyserial
```

Then either run `example.py` from this folder or install the package locally.

## Main commands

```python
stage.get_position_mm()

stage.set_max_speed_mm_s(
    max_speed_mm_s=10,
    start_speed_mm_s=0.5,
    accel_time_ms=200,
)

stage.step_forward(0.1)
stage.step_backward(0.1)

stage.move_relative_mm(1.0)
stage.move_absolute_mm(10.0)

stage.home("-")
stage.stop()
```

## Important

The GSC-02C is an open-loop stepper controller. Its reported position is based
on commanded motor pulses, not independent encoder feedback. Home the system
appropriately before depending on absolute coordinates.
