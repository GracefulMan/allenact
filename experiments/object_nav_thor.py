from typing import Dict, Any, List

import gym
import numpy as np
import torch.nn as nn
import torch.optim as optim

from configs.losses import algo_defaults
from configs.util import Builder
from extensions.ai2thor.models.object_nav_models import ObjectNavBaselineActorCritic
from extensions.ai2thor.sensors import RGBSensorThor
from extensions.ai2thor.task_samplers import ObjectNavTaskSampler
from extensions.ai2thor.tasks import ObjectNavTask
from imitation.trainer import Imitation
from imitation.utils import LinearDecay
from onpolicy_sync.losses import PPO
from rl_base.experiment_config import ExperimentConfig
from rl_base.sensor import SensorSuite
from rl_base.task import TaskSampler


##
# ObjectNav configuration example
##
class ObjectNavThorExperimentConfig(ExperimentConfig):
    OBJECT_TYPES = ["Tomato", "Cup", "Television"]

    SCREEN_SIZE = 224

    SENSORS = [
        RGBSensorThor(
            {
                "height": SCREEN_SIZE,
                "width": SCREEN_SIZE,
                "use_resnet_normalization": True,
            }
        ),
    ]

    ENV_ARGS = {
        "player_screen_height": SCREEN_SIZE,
        "player_screen_width": SCREEN_SIZE,
        "quality": "Very Low",
    }

    @classmethod
    def tag(cls):
        return "ObjectNav"

    @classmethod
    def training_pipeline(cls, **kwargs):
        dagger_steps = 1000
        ppo_steps = 100000
        nprocesses = 10
        lr = 2.5e-4
        num_mini_batch = 3
        update_repeats = 1
        num_steps = 128
        gpu_ids = [0, 1, 2]
        return {
            "optimizer": Builder(optim.Adam, dict(lr=lr)),
            "nprocesses": nprocesses,
            "num_mini_batch": num_mini_batch,
            "update_repeats": update_repeats,
            "num_steps": num_steps,
            "gpu_ids": gpu_ids,
            "imitation_loss": Builder(Imitation,),
            "ppo_loss": Builder(
                PPO,
                dict(ppo_epoch=update_repeats, num_mini_batch=num_mini_batch),
                default=algo_defaults["ppo_loss"],
            ),
            "pipeline": [
                {
                    "losses": ["imitation_loss"],
                    "teacher_forcing": Builder(
                        LinearDecay, dict(startp=1, endp=1e-6, steps=dagger_steps)
                    ),
                    "end_criterion": dagger_steps,
                },
                {"losses": ["ppo_loss", "imitation_loss"], "end_criterion": ppo_steps},
            ],
        }

    @classmethod
    def create_model(cls, **kwargs) -> nn.Module:
        return ObjectNavBaselineActorCritic(
            action_space=gym.spaces.Discrete(len(ObjectNavTask.action_names())),
            observation_space=SensorSuite(cls.SENSORS).observation_spaces,
            goal_sensor_uuid="object_type",
            hidden_size=512,
            object_type_embedding_dim=8,
        )

    @staticmethod
    def make_sampler_fn(**kwargs) -> TaskSampler:
        return ObjectNavTaskSampler(**kwargs)

    @staticmethod
    def _partition_inds(n: int, num_parts: int):
        m = n // num_parts
        parts = [m] * num_parts
        num_extra = n % num_parts
        for i in range(num_extra):
            parts[i] += 1
        return np.cumsum(parts)

    def _get_sampler_args_for_scene_split(
        self, scenes: List[str], process_ind: int, total_processes: int
    ) -> Dict[str, Any]:
        assert total_processes <= len(scenes), "More processes than scenes."
        inds = [0] + self._partition_inds(len(scenes), total_processes)

        return {
            "scenes": scenes[inds[process_ind] : inds[process_ind + 1]],
            "object_type": self.OBJECT_TYPES,
            "env_args": self.ENV_ARGS,
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
