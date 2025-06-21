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
        raise RuntimeError(
            "Could not find follower host. "
            "Ensure the follower server is running and specify --network-range if needed."
        )
    logging.info("Connecting to follower at %s:%d", ip, cfg.port)

    try:
        sock = socket.create_connection((ip, cfg.port))
    except OSError as err:
        raise RuntimeError(
            f"Unable to connect to follower at {ip}:{cfg.port}: {err}\n"
            "Check that the server is reachable and no firewall blocks the connection."
        ) from err

    buffer = b""
    while b"\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise RuntimeError("Connection closed by follower during handshake")
        buffer += chunk
    try:
        handshake = json.loads(buffer.split(b"\n", 1)[0].decode())
        logging.info("Follower handshake: %s", handshake)
    except json.JSONDecodeError as err:
        sock.close()
        raise RuntimeError(
            f"Invalid handshake from follower: {err}\n"
            "Ensure both machines run compatible versions of LeRobot."
        ) from err
    teleop = make_teleoperator_from_config(cfg.teleop)
    teleop.connect()

    try:
        while True:
            loop_start = time.perf_counter()
            action = teleop.get_action()
            try:
                sock.sendall(json.dumps(action).encode() + b"\n")
            except OSError as err:
                logging.error("Lost connection to follower: %s", err)
                logging.error("Restart the follower server and check your network connection.")
                break
            busy_wait(1 / cfg.fps - (time.perf_counter() - loop_start))
    except KeyboardInterrupt:
        pass
    finally:
        teleop.disconnect()
        sock.close()


if __name__ == "__main__":
    main()
