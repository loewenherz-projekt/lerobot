#!/usr/bin/env python

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Server for remotely controlling a SO100 follower arm."""

import base64
import contextlib
import json
import logging
import socket
import threading
import time
from dataclasses import dataclass

import draccus

import cv2
import zmq

from .config_so100_follower import SO100FollowerConfig
from .so100_follower import SO100Follower


@dataclass
class SO100FollowerServerConfig:
    port_zmq_cmd: int = 5555
    port_zmq_observations: int = 5556
    discovery_port: int = 5005
    connection_time_s: int = 30
    watchdog_timeout_ms: int = 500
    max_loop_freq_hz: int = 30


@dataclass
class SO100FollowerServerCLIConfig:
    robot: SO100FollowerConfig
    server: SO100FollowerServerConfig = SO100FollowerServerConfig()


class SO100FollowerServer:
    def __init__(self, config: SO100FollowerServerConfig):
        self.port_zmq_cmd = config.port_zmq_cmd
        self.zmq_context = zmq.Context()
        self.zmq_cmd_socket = self.zmq_context.socket(zmq.PULL)
        self.zmq_cmd_socket.setsockopt(zmq.CONFLATE, 1)
        self.zmq_cmd_socket.bind(f"tcp://*:{config.port_zmq_cmd}")

        self.zmq_observation_socket = self.zmq_context.socket(zmq.PUSH)
        self.zmq_observation_socket.setsockopt(zmq.CONFLATE, 1)
        self.zmq_observation_socket.bind(f"tcp://*:{config.port_zmq_observations}")

        self.discovery_port = config.discovery_port
        self._running = True
        self._discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._discovery_socket.bind(("", self.discovery_port))
        self._discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self._discovery_thread.start()

        self.connection_time_s = config.connection_time_s
        self.watchdog_timeout_ms = config.watchdog_timeout_ms
        self.max_loop_freq_hz = config.max_loop_freq_hz

    def _discovery_loop(self) -> None:
        while self._running:
            try:
                data, addr = self._discovery_socket.recvfrom(1024)
                if data == b"LEROBOT_DISCOVERY":
                    self._discovery_socket.sendto(str(self.port_zmq_cmd).encode(), addr)
            except OSError:
                break

    def disconnect(self) -> None:
        self._running = False
        with contextlib.suppress(OSError):
            self._discovery_socket.close()
        self.zmq_observation_socket.close()
        self.zmq_cmd_socket.close()
        self.zmq_context.term()


@draccus.wrap()
def main(cfg: SO100FollowerServerCLIConfig) -> None:
    logging.basicConfig(level=logging.INFO)
    logging.info("Configuring SO100 follower")
    robot = SO100Follower(cfg.robot)

    logging.info("Connecting SO100 follower")
    robot.connect()

    host = SO100FollowerServer(cfg.server)

    last_cmd_time = time.time()
    watchdog_active = False
    logging.info("Waiting for commands...")
    try:
        start = time.perf_counter()
        duration = 0
        while duration < host.connection_time_s:
            loop_start_time = time.time()
            try:
                msg = host.zmq_cmd_socket.recv_string(zmq.NOBLOCK)
                data = dict(json.loads(msg))
                robot.send_action(data)
                last_cmd_time = time.time()
                watchdog_active = False
            except zmq.Again:
                if not watchdog_active:
                    logging.warning("No command available")
            except Exception as e:  # noqa: BLE001
                logging.error("Message fetching failed: %s", e)

            now = time.time()
            if (now - last_cmd_time > host.watchdog_timeout_ms / 1000) and not watchdog_active:
                logging.warning(
                    f"Command not received for more than {host.watchdog_timeout_ms} milliseconds."
                )
                watchdog_active = True

            last_observation = robot.get_observation()

            for cam_key in robot.cameras:
                ret, buffer = cv2.imencode(
                    ".jpg", last_observation[cam_key], [int(cv2.IMWRITE_JPEG_QUALITY), 90]
                )
                if ret:
                    last_observation[cam_key] = base64.b64encode(buffer).decode("utf-8")
                else:
                    last_observation[cam_key] = ""

            try:
                host.zmq_observation_socket.send_string(json.dumps(last_observation), flags=zmq.NOBLOCK)
            except zmq.Again:
                logging.info("Dropping observation, no client connected")

            elapsed = time.time() - loop_start_time
            time.sleep(max(1 / host.max_loop_freq_hz - elapsed, 0))
            duration = time.perf_counter() - start
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received. Exiting...")
    finally:
        logging.info("Shutting down SO100 follower server.")
        robot.disconnect()
        host.disconnect()

    logging.info("Finished SO100 follower cleanly")


if __name__ == "__main__":
    main()
