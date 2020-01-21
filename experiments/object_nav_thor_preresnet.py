from typing import Dict, Any, List

import gym
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import models
import copy

from configs.losses import algo_defaults
from configs.util import Builder
from extensions.ai2thor.models.object_nav_models import ObjectNavBaselineActorCritic
from extensions.ai2thor.sensors import RGBSensorThor, GoalObjectTypeThorSensor
from extensions.ai2thor.preprocessors import ResnetPreProcessorThor
from extensions.ai2thor.task_samplers import ObjectNavTaskSampler
from extensions.ai2thor.tasks import ObjectNavTask
from imitation.utils import LinearDecay
from onpolicy_sync.losses import PPO
from onpolicy_sync.losses.imitation import Imitation
from rl_base.experiment_config import ExperimentConfig
from rl_base.sensor import SensorSuite, ExpertActionSensor
from rl_base.task import TaskSampler


class ObjectNavThorPreResnetExperimentConfig(ExperimentConfig):
    """An object navigation experiment in THOR."""

    OBJECT_TYPES = sorted(["Cup", "Television", "Tomato"])

    SCREEN_SIZE = 224

    GPUS = None if not torch.cuda.is_available() else [0]

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

    OBSERVATIONS = [
        Builder(
            ResnetPreProcessorThor,
            {
                "config": {
                    "input_height": SCREEN_SIZE,
                    "input_width": SCREEN_SIZE,
                    "output_width": 7,
                    "output_height": 7,
                    "output_dims": 512,
                    "torchvision_resnet_model": models.resnet18,
                    "input_uuids": ["rgb"],
                    "output_uuid": "resnet",
                }
            },
        ),
        "goal_object_type_ind",
        "rgb",
    ]

    ENV_ARGS = {
        "player_screen_height": SCREEN_SIZE,
        "player_screen_width": SCREEN_SIZE,
        "quality": "Very Low",
    }

    MAX_STEPS = 4

    @classmethod
    def tag(cls):
        return "ObjectNav"

    @classmethod
    def training_pipeline(cls, **kwargs):
        dagger_steps = 1000
        ppo_steps = 10
        nprocesses = 2
        lr = 2.5e-4
        num_mini_batch = 2
        update_repeats = 2
        num_steps = 4
        gpu_ids = cls.GPUS
        return {
            "optimizer": Builder(optim.Adam, dict(lr=lr)),
            "nprocesses": nprocesses,
            "num_mini_batch": num_mini_batch,
            "update_repeats": update_repeats,
            "num_steps": num_steps,
            "gpu_ids": gpu_ids,
            "imitation_loss": Builder(Imitation,),
            "ppo_loss": Builder(PPO, dict(), default=algo_defaults["ppo_loss"],),
            "observation_set": cls.OBSERVATIONS,
            "pipeline": [
                # {
                #     "losses": ["imitation_loss", "ppo_loss"],
                #     "teacher_forcing": Builder(
                #         LinearDecay, dict(startp=1, endp=1e-6, steps=dagger_steps)
                #     ),
                #     "end_criterion": dagger_steps,
                # },
                # {"losses": ["ppo_loss", "imitation_loss"], "end_criterion": ppo_steps},
                {"losses": ["ppo_loss"], "end_criterion": ppo_steps},
            ],
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

    @classmethod
    def _process_to_device(cls, n: int) -> torch.device:
        return torch.device(
            "cpu" if len(cls.GPUS) == 0 else "cuda:%d" % cls.GPUS[(n % len(cls.GPUS))]
        )

    def _get_sampler_args_for_scene_split(
        self, scenes: List[str], process_ind: int, total_processes: int
    ) -> Dict[str, Any]:
        assert total_processes <= len(scenes), "More processes than scenes."
        inds = self._partition_inds(len(scenes), total_processes)

        return {
            "scenes": scenes[inds[process_ind] : inds[process_ind + 1]],
            "object_types": self.OBJECT_TYPES,
            "sensors": self.SENSORS,
            "env_args": self.ENV_ARGS,
            "max_steps": self.MAX_STEPS,
            "action_space": gym.spaces.Discrete(len(ObjectNavTask.action_names())),
        }

    def train_task_sampler_args(
        self, process_ind: int, total_processes: int
    ) -> Dict[str, Any]:
        all_train_scenes = ["FloorPlan{}".format(i) for i in range(1, 21)]
        return self._get_sampler_args_for_scene_split(
            all_train_scenes, process_ind, total_processes
        )

    def valid_task_sampler_args(
        self, process_ind: int, total_processes: int
    ) -> Dict[str, Any]:
        all_valid_scenes = ["FloorPlan{}".format(i) for i in range(21, 26)]
        return self._get_sampler_args_for_scene_split(
            all_valid_scenes, process_ind, total_processes
        )

    def test_task_sampler_args(
        self, process_ind: int, total_processes: int
    ) -> Dict[str, Any]:
        all_test_scenes = ["FloorPlan{}".format(i) for i in range(26, 31)]
        return self._get_sampler_args_for_scene_split(
            all_test_scenes, process_ind, total_processes
        )
