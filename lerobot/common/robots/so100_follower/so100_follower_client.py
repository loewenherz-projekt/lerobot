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

"""Client interface to control a remote SO100 follower arm."""

import base64
import json
import logging
from functools import cached_property
from typing import Any, Dict, Optional

import cv2
import numpy as np
import zmq

from lerobot.common.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from ..robot import Robot
from ..utils import discover_server
from .config_so100_follower import SO100FollowerClientConfig

logger = logging.getLogger(__name__)


class SO100FollowerClient(Robot):
    config_class = SO100FollowerClientConfig
    name = "so100_follower_client"

    def __init__(self, config: SO100FollowerClientConfig):
        super().__init__(config)
        self.config = config
        self.remote_ip = config.remote_ip
        self.port_zmq_cmd = config.port_zmq_cmd
        self.port_zmq_observations = config.port_zmq_observations
        self.polling_timeout_ms = config.polling_timeout_ms
        self.connect_timeout_s = config.connect_timeout_s

        self.zmq_context = None
        self.zmq_cmd_socket = None
        self.zmq_observation_socket = None
        self._is_connected = False
        self.last_observation: Dict[str, Any] = {}

    @cached_property
    def _motors_ft(self) -> Dict[str, type]:
        return {
            "shoulder_pan.pos": float,
            "shoulder_lift.pos": float,
            "elbow_flex.pos": float,
            "wrist_flex.pos": float,
            "wrist_roll.pos": float,
            "gripper.pos": float,
        }

    @cached_property
    def _cameras_ft(self) -> Dict[str, tuple[int, int, int]]:
        return {name: (cfg.height, cfg.width, 3) for name, cfg in self.config.cameras.items()}

    @cached_property
    def observation_features(self) -> Dict[str, type | tuple]:
        return {**self._motors_ft, **self._cameras_ft}

    @cached_property
    def action_features(self) -> Dict[str, type]:
        return self._motors_ft

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def is_calibrated(self) -> bool:
        return True

    def connect(self) -> None:
        if self._is_connected:
            raise DeviceAlreadyConnectedError("SO100FollowerClient already connected")

        if self.remote_ip is None:
            result = discover_server(port=self.port_zmq_cmd)
            if result is None:
                raise DeviceNotConnectedError("Could not discover follower server")
            self.remote_ip, self.port_zmq_cmd = result

        self.zmq_context = zmq.Context()
        self.zmq_cmd_socket = self.zmq_context.socket(zmq.PUSH)
        self.zmq_cmd_socket.connect(f"tcp://{self.remote_ip}:{self.port_zmq_cmd}")
        self.zmq_cmd_socket.setsockopt(zmq.CONFLATE, 1)

        self.zmq_observation_socket = self.zmq_context.socket(zmq.PULL)
        self.zmq_observation_socket.connect(f"tcp://{self.remote_ip}:{self.port_zmq_observations}")
        self.zmq_observation_socket.setsockopt(zmq.CONFLATE, 1)

        poller = zmq.Poller()
        poller.register(self.zmq_observation_socket, zmq.POLLIN)
        socks = dict(poller.poll(self.connect_timeout_s * 1000))
        if self.zmq_observation_socket not in socks or socks[self.zmq_observation_socket] != zmq.POLLIN:
            raise DeviceNotConnectedError("Timeout waiting for follower server to connect")

        self._is_connected = True

    def calibrate(self) -> None:
        pass

    def _poll_and_get_latest_message(self) -> Optional[str]:
        poller = zmq.Poller()
        poller.register(self.zmq_observation_socket, zmq.POLLIN)
        try:
            socks = dict(poller.poll(self.polling_timeout_ms))
        except zmq.ZMQError as e:  # noqa: BLE001
            logger.error("ZMQ polling error: %s", e)
            return None

        if self.zmq_observation_socket not in socks:
            return None

        last_msg = None
        while True:
            try:
                msg = self.zmq_observation_socket.recv_string(zmq.NOBLOCK)
                last_msg = msg
            except zmq.Again:
                break
        return last_msg

    def _decode_image(self, image_b64: str) -> Optional[np.ndarray]:
        if not image_b64:
            return None
        try:
            jpg_data = base64.b64decode(image_b64)
            np_arr = np.frombuffer(jpg_data, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            return frame
        except Exception as e:  # noqa: BLE001
            logger.error("Error decoding image: %s", e)
            return None

    def get_observation(self) -> Dict[str, Any]:
        if not self._is_connected:
            raise DeviceNotConnectedError("SO100FollowerClient is not connected")

        msg = self._poll_and_get_latest_message()
        if msg is None:
            return self.last_observation

        try:
            obs = json.loads(msg)
        except json.JSONDecodeError as e:  # noqa: BLE001
            logger.error("Error decoding JSON: %s", e)
            return self.last_observation

        for cam_name in self._cameras_ft:
            frame = self._decode_image(obs.get(cam_name, ""))
            if frame is not None:
                obs[cam_name] = frame
            else:
                obs.pop(cam_name, None)
        self.last_observation = obs
        return obs

    def send_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if not self._is_connected:
            raise DeviceNotConnectedError("SO100FollowerClient is not connected")
        self.zmq_cmd_socket.send_string(json.dumps(action))
        return action

    def configure(self) -> None:
        pass

    def disconnect(self) -> None:
        if not self._is_connected:
            raise DeviceNotConnectedError("SO100FollowerClient is not connected")
        self.zmq_observation_socket.close()
        self.zmq_cmd_socket.close()
        self.zmq_context.term()
        self._is_connected = False
