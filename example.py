from optosigma_gsc02c import GSC02C


# Change this to the serial port used by your controller.
#
# Windows:
#     "COM3"
#     "COM7"
#
# Linux:
#     "/dev/ttyUSB0"
#
PORT = "COM7"


# Using "with" automatically opens the serial connection at the beginning
# and closes it safely when the block finishes.
with GSC02C(PORT, axis=1) as stage:

    # --------------------------------------------------------------
    # READ CURRENT POSITION
    # --------------------------------------------------------------

    # This is the controller's calculated pulse position converted to mm.
    print(
        "Current position:",
        stage.get_position_mm(),
        "mm",
    )

    # --------------------------------------------------------------
    # SET SPEED AND ACCELERATION
    # --------------------------------------------------------------

    stage.set_max_speed_mm_s(
        max_speed_mm_s=10.0,    # maximum translation speed
        start_speed_mm_s=0.5,   # speed when motion begins
        accel_time_ms=200,      # acceleration/deceleration ramp time
    )

    # --------------------------------------------------------------
    # SG-SAMPLE-LIKE STEP CONTROLS
    # --------------------------------------------------------------

    # Move forward by 100 micrometers.
    # 0.100 mm = 100 um.
    stage.step_forward(0.100)

    # Move backward by 50 micrometers.
    stage.step_backward(0.050)

    # --------------------------------------------------------------
    # RELATIVE MOVE
    # --------------------------------------------------------------

    # Move +1 mm relative to wherever the stage currently is.
    stage.move_relative_mm(1.0)

    # Negative values move backward:
    #
    # stage.move_relative_mm(-1.0)

    # --------------------------------------------------------------
    # ABSOLUTE MOVE
    # --------------------------------------------------------------

    # Move to the controller coordinate 10 mm.
    stage.move_absolute_mm(10.0)

    # --------------------------------------------------------------
    # FINAL POSITION
    # --------------------------------------------------------------

    print(
        "Final position:",
        stage.get_position_mm(),
        "mm",
    )

    # --------------------------------------------------------------
    # OTHER COMMANDS
    # --------------------------------------------------------------

    # Home toward the negative direction:
    #
    # stage.home("-")

    # Controlled stop:
    #
    # stage.stop()
