#!/usr/bin/env python

"""Simple script to teleoperate Stretch3 using an Xbox controller."""

from __future__ import annotations

import argparse
import logging

from lerobot.common.robots.stretch3 import Stretch3, Stretch3RobotConfig
from lerobot.common.teleoperators.stretch3_gamepad import (
    Stretch3GamePad,
    Stretch3GamePadConfig,
)
from lerobot.teleoperate import teleop_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Teleoperate Stretch3 with a gamepad")
    parser.add_argument("--fps", type=int, default=60, help="Maximum teleoperation frequency")
    parser.add_argument(
        "--display-data",
        action="store_true",
        help="Display camera feeds using rerun",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Time in seconds to teleoperate before exiting",
    )
    args = parser.parse_args()

    robot = Stretch3(Stretch3RobotConfig())
    teleop = Stretch3GamePad(Stretch3GamePadConfig())

    robot.connect()
    teleop.connect()

    try:
        teleop_loop(
            teleop,
            robot,
            args.fps,
            display_data=args.display_data,
            duration=args.duration,
        )
    except KeyboardInterrupt:
        pass
    finally:
        teleop.disconnect()
        robot.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
