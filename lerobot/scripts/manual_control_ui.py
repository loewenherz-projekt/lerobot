#!/usr/bin/env python

"""Simple Tkinter GUI to manually control a SO101 follower arm.

Example:
    python lerobot/scripts/manual_control_ui.py --port /dev/ttyUSB0 --id my_arm
"""

from __future__ import annotations

import argparse
import tkinter as tk

from lerobot.common.motors import MotorNormMode
from lerobot.common.robots.so101_follower import SO101Follower, SO101FollowerConfig


def _norm_from_raw(bus, motor: str, raw: int) -> float:
    calib = bus.calibration[motor]
    min_r = calib.range_min
    max_r = calib.range_max
    drive_mode = bus.apply_drive_mode and calib.drive_mode
    if bus.motors[motor].norm_mode is MotorNormMode.RANGE_M100_100:
        norm = ((raw - min_r) / (max_r - min_r)) * 200 - 100
        return -norm if drive_mode else norm
    if bus.motors[motor].norm_mode is MotorNormMode.RANGE_0_100:
        norm = ((raw - min_r) / (max_r - min_r)) * 100
        return 100 - norm if drive_mode else norm
    if bus.motors[motor].norm_mode is MotorNormMode.DEGREES:
        mid = (min_r + max_r) / 2
        max_res = bus.model_resolution_table[bus._id_to_model(calib.id)] - 1
        return (raw - mid) * 360 / max_res
    raise NotImplementedError


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual control UI for SO101 follower arm")
    parser.add_argument("--port", required=True, help="Serial port of the arm")
    parser.add_argument("--id", default="so101_manual", help="Robot identifier")
    args = parser.parse_args()

    cfg = SO101FollowerConfig(port=args.port, id=args.id)
    robot = SO101Follower(cfg)
    robot.connect(calibrate=False)

    calib = robot.bus.read_calibration()

    root = tk.Tk()
    root.title("SO101 Manual Control")

    entries: dict[str, tk.Entry] = {}
    pos_labels: dict[str, tk.StringVar] = {}

    row = 0
    for motor in robot.bus.motors:
        mcal = calib[motor]
        nmin = _norm_from_raw(robot.bus, motor, mcal.range_min)
        nmax = _norm_from_raw(robot.bus, motor, mcal.range_max)
        label = tk.Label(root, text=f"{motor} ({nmin:.1f} to {nmax:.1f})")
        label.grid(row=row, column=0, padx=5, pady=5)
        entry = tk.Entry(root, width=10)
        entry.grid(row=row, column=1, padx=5, pady=5)
        entries[motor] = entry
        pos_var = tk.StringVar()
        pos_label = tk.Label(root, textvariable=pos_var)
        pos_label.grid(row=row, column=2, padx=5, pady=5)
        pos_labels[motor] = pos_var
        row += 1

    def move() -> None:
        action = {}
        for motor, entry in entries.items():
            val = entry.get().strip()
            if not val:
                continue
            try:
                action[f"{motor}.pos"] = float(val)
            except ValueError:
                continue
        if action:
            robot.send_action(action)

    def update_positions() -> None:
        obs = robot.bus.sync_read("Present_Position")
        for motor, pos in obs.items():
            pos_labels[motor].set(f"{pos:.1f}")
        root.after(100, update_positions)

    move_btn = tk.Button(root, text="Move", command=move)
    move_btn.grid(row=row, column=0, columnspan=2, pady=10)
    update_positions()

    def on_close() -> None:
        robot.disconnect()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
