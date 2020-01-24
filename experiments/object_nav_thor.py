from math import ceil
from typing import Dict, Any, List, Optional

import gym
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from configs.losses import PPOConfig
from configs.util import Builder
from extensions.ai2thor.models.object_nav_models import ObjectNavBaselineActorCritic
from extensions.ai2thor.sensors import RGBSensorThor, GoalObjectTypeThorSensor
from extensions.ai2thor.task_samplers import ObjectNavTaskSampler
from extensions.ai2thor.tasks import ObjectNavTask
from onpolicy_sync.utils import LinearDecay
from onpolicy_sync.losses import PPO
from onpolicy_sync.losses.imitation import Imitation
from rl_base.experiment_config import ExperimentConfig
from rl_base.sensor import SensorSuite, ExpertActionSensor
from rl_base.task import TaskSampler


class ObjectNavThorExperimentConfig(ExperimentConfig):
    """An object navigation experiment in THOR."""

    # OBJECT_TYPES = sorted(["Cup", "Television", "Tomato"])
    OBJECT_TYPES = sorted(["Tomato"])
    TRAIN_SCENES = [
        "FloorPlan1_physics"
    ]  # ["FloorPlan{}".format(i) for i in range(1, 21)]
    VALID_SCENES = ["FloorPlan{}_physics".format(i) for i in range(21, 26)]
    TEST_SCENSE = ["FloorPlan{}_physics".format(i) for i in range(26, 31)]

    SCREEN_SIZE = 224

    SENSORS = [
        RGBSensorThor(
            {
                "height": SCREEN_SIZE,
                "width": SCREEN_SIZE,
                "use_resnet_normalization": True,
            }
        ),
        GoalObjectTypeThorSensor({"object_types": OBJECT_TYPES}),
        ExpertActionSensor({"nactions": 6}),
    ]

    ENV_ARGS = {
        "player_screen_height": SCREEN_SIZE,
        "player_screen_width": SCREEN_SIZE,
        "quality": "Very Low",
    }

    MAX_STEPS = 128

    SCENE_PERIOD = 10

    VALID_SAMPLES_IN_SCENE = 2

    @classmethod
    def tag(cls):
        return "ObjectNav"

    @classmethod
    def training_pipeline(cls, **kwargs):
        dagger_steps = 3e4
        ppo_steps = 3e4
        ppo_steps2 = 1e6
        nprocesses = 4
        lr = 2.5e-4
        num_mini_batch = 1
        update_repeats = 2
        num_steps = 16
        save_interval = 100
        log_interval = 2 * num_steps * nprocesses
        gpu_ids = [] if not torch.cuda.is_available() else [1]
        gamma = 0.99
        use_gae = True
        gae_lambda = 1.0
        max_grad_norm = 0.5
        return {
            "save_interval": save_interval,
            "log_interval": log_interval,
            "optimizer": Builder(optim.Adam, dict(lr=lr)),
            "nprocesses": nprocesses,
            "num_mini_batch": num_mini_batch,
            "update_repeats": update_repeats,
            "num_steps": num_steps,
            "gpu_ids": gpu_ids,
            "imitation_loss": Builder(Imitation,),
            "ppo_loss": Builder(PPO, dict(), default=PPOConfig,),
            "gamma": gamma,
            "use_gae": use_gae,
            "gae_lambda": gae_lambda,
            "max_grad_norm": max_grad_norm,
            "pipeline": [
                {
                    "losses": ["imitation_loss", "ppo_loss"],
                    "teacher_forcing": LinearDecay(
                        startp=1.0, endp=0.0, steps=dagger_steps,
                    ),
                    "end_criterion": dagger_steps,
                },
                {"losses": ["ppo_loss", "imitation_loss"], "end_criterion": ppo_steps,},
                {"losses": ["ppo_loss"], "end_criterion": ppo_steps2,},
            ],
        }

    @classmethod
    def evaluation_params(cls, **kwargs):
        nprocesses = 5
        gpu_ids = [] if not torch.cuda.is_available() else [2]
        return {
            "nprocesses": nprocesses,
            "gpu_ids": gpu_ids,
        }

    @classmethod
    def create_model(cls, **kwargs) -> nn.Module:
        return ObjectNavBaselineActorCritic(
            action_space=gym.spaces.Discrete(len(ObjectNavTask.action_names())),
            observation_space=SensorSuite(cls.SENSORS).observation_spaces,
            goal_sensor_uuid="goal_object_type_ind",
            hidden_size=512,
            object_type_embedding_dim=8,
        )

    @staticmethod
    def make_sampler_fn(**kwargs) -> TaskSampler:
        return ObjectNavTaskSampler(**kwargs)

    @staticmethod
    def _partition_inds(n: int, num_parts: int):
        return np.round(np.linspace(0, n, num_parts + 1, endpoint=True)).astype(
            np.int32
        )

    def _get_sampler_args_for_scene_split(
        self, scenes: List[str], process_ind: int, total_processes: int
    ) -> Dict[str, Any]:
        if len(scenes) % total_processes != 0:
            print(
                "Warning: oversampling some of the scenes to feed all processes. You can avoid this by setting a number of workers divisor of the number of scenes"
            )
        if total_processes > len(scenes):  # oversample some scenes -> bias
            if total_processes % len(scenes) != 0:
                print(
                    "Warning: oversampling some of the scenes to feed all processes. You can avoid this by setting a number of workers divisible by the number of scenes"
                )
            scenes = scenes * int(ceil(total_processes / len(scenes)))
            scenes = scenes[: total_processes * (len(scenes) // total_processes)]
        inds = self._partition_inds(len(scenes), total_processes)

        return {
            "scenes": scenes[inds[process_ind] : inds[process_ind + 1]],
            "object_types": self.OBJECT_TYPES,
            "env_args": self.ENV_ARGS,
            "max_steps": self.MAX_STEPS,
            "sensors": self.SENSORS,
            "action_space": gym.spaces.Discrete(len(ObjectNavTask.action_names())),
        }

    def train_task_sampler_args(
        self,
        process_ind: int,
        total_processes: int,
        devices: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        res = self._get_sampler_args_for_scene_split(
            self.TRAIN_SCENES, process_ind, total_processes
        )
        res["scene_period"] = self.SCENE_PERIOD
        res["env_args"]["x_display"] = (
            "0.%d" % devices[0] if len(devices) >= 0 else None
        )
        return res

    def valid_task_sampler_args(
        self, process_ind: int, total_processes: int, devices: Optional[List[int]]
    ) -> Dict[str, Any]:
        res = self._get_sampler_args_for_scene_split(
            self.VALID_SCENES, process_ind, total_processes
        )
        res["scene_period"] = self.VALID_SAMPLES_IN_SCENE
        res["max_tasks"] = self.VALID_SAMPLES_IN_SCENE * len(res["scenes"])
        res["env_args"]["x_display"] = (
            "0.%d" % devices[0] if len(devices) >= 0 else None
        )
        return res

    def test_task_sampler_args(
        self, process_ind: int, total_processes: int, devices: Optional[List[int]]
    ) -> Dict[str, Any]:
        res = self._get_sampler_args_for_scene_split(
            self.TEST_SCENSE, process_ind, total_processes
        )
        res["env_args"]["x_display"] = (
            "0.%d" % devices[0] if len(devices) >= 0 else None
        )
        return res
