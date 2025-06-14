#!/usr/bin/env python

"""Run the robot follower as a TCP server."""

from __future__ import annotations

import json
import logging
import socket
from dataclasses import dataclass

import draccus

from lerobot.common.robots import RobotConfig, make_robot_from_config
from lerobot.common.utils.utils import init_logging


@dataclass
class FollowerServerConfig:
    robot: RobotConfig
    port: int = 5555


@draccus.wrap()
def main(cfg: FollowerServerConfig) -> None:
    init_logging()
    robot = make_robot_from_config(cfg.robot)
    robot.connect()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("", cfg.port))
    server.listen(1)
    logging.info("Waiting for leader connection on port %d", cfg.port)
    conn, addr = server.accept()
    logging.info("Leader connected from %s", addr)

    buffer = b""
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line:
                    continue
                action = json.loads(line.decode())
                robot.send_action(action)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
        server.close()
        robot.disconnect()


if __name__ == "__main__":
    main()
