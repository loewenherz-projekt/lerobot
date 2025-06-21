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
    try:
        robot.connect()
    except Exception as err:  # pragma: no cover - just logs
        logging.error("Failed to connect to robot: %s", err)
        logging.error("Verify the robot's USB connection and permissions.")
        return

    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("", cfg.port))
        server.listen(1)
    except OSError as err:  # pragma: no cover - just logs
        logging.error("Could not open port %d: %s", cfg.port, err)
        logging.error("Make sure the port is free and the firewall allows incoming connections.")
        robot.disconnect()
        return

    logging.info("Waiting for leader connection on port %d", cfg.port)
    conn, addr = server.accept()
    logging.info("Leader connected from %s", addr)

    try:
        handshake = {"status": "ready", "action_features": list(robot.action_features.keys())}
        conn.sendall(json.dumps(handshake).encode() + b"\n")
    except OSError as err:  # pragma: no cover - just logs
        logging.error("Failed to send handshake: %s", err)
        conn.close()
        server.close()
        robot.disconnect()
        return

    buffer = b""
    try:
        while True:
            try:
                data = conn.recv(4096)
            except OSError as err:  # pragma: no cover - just logs
                logging.error("Failed to receive data: %s", err)
                logging.error("Check your network connection.")
                break

            if not data:
                logging.warning("Leader disconnected")
                break
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line:
                    continue
                try:
                    action = json.loads(line.decode())
                except json.JSONDecodeError as err:  # pragma: no cover - just logs
                    logging.error("Malformed message from leader: %s", err)
                    logging.error("Ensure both scripts run the same version of LeRobot.")
                    continue

                try:
                    robot.send_action(action)
                except Exception as err:  # pragma: no cover - just logs
                    logging.error("Failed to execute action: %s", err)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
        server.close()
        robot.disconnect()


if __name__ == "__main__":
    main()
