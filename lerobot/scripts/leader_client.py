#!/usr/bin/env python

"""Leader script that discovers the follower and sends teleop actions."""

from __future__ import annotations

import json
import logging
import socket
import time
from dataclasses import dataclass

import draccus

from lerobot.common.network_utils import discover_host
from lerobot.common.teleoperators import TeleoperatorConfig, make_teleoperator_from_config
from lerobot.common.utils.robot_utils import busy_wait
from lerobot.common.utils.utils import init_logging


@dataclass
class LeaderClientConfig:
    teleop: TeleoperatorConfig
    port: int = 5555
    network_range: str | None = None
    fps: int = 60


@draccus.wrap()
def main(cfg: LeaderClientConfig) -> None:
    init_logging()
    ip = discover_host(cfg.port, cfg.network_range)
    if ip is None:
        raise RuntimeError("Could not find follower host")
    logging.info("Connecting to follower at %s:%d", ip, cfg.port)

    sock = socket.create_connection((ip, cfg.port))
    teleop = make_teleoperator_from_config(cfg.teleop)
    teleop.connect()

    try:
        while True:
            loop_start = time.perf_counter()
            action = teleop.get_action()
            sock.sendall(json.dumps(action).encode() + b"\n")
            busy_wait(1 / cfg.fps - (time.perf_counter() - loop_start))
    except KeyboardInterrupt:
        pass
    finally:
        teleop.disconnect()
        sock.close()


if __name__ == "__main__":
    main()
