from rl_base.experiment_config import ExperimentConfig
import torch.optim as optim
import torch.nn as nn
import numpy as np
from typing import Dict, Any, List
from a2c_ppo_acktr.algo import PPO
from imitation.trainer import Imitation
from models import ObjectNavThorModel
from imitation.utils import LinearDecay


##
# ObjectNav configuration example
##
class ObjectNavThorExperimentConfig(ExperimentConfig):
    OBJECT_TYPES = ["Tomato", "Cup", "Television"]

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
            "optimizer": optim.Adam,
            "lr": lr,
            "nproccesses": nprocesses,
            "num_mini_batch": num_mini_batch,
            "update_repeats": update_repeats,
            "num_steps": num_steps,
            "gpu_ids": gpu_ids,
            "pipeline": [
                {
                    "losses": [Imitation],
                    "teacher_forcing": LinearDecay(
                        startp=1, endp=0, steps=dagger_steps
                    ),
                    "end_criteria": dagger_steps,
                },
                {"losses": [PPO, Imitation], "end_criteria": ppo_steps},
            ],
        }

    @classmethod
    def create_model(cls, **kwargs) -> nn.Module:
        return ObjectNavThorModel()

    @staticmethod
    def _partition_inds(n: int, num_parts: int):
        m = n // num_parts
        parts = [m] * num_parts
        num_extra = n % num_parts
        for i in range(num_extra):
            parts[i] += 1
        return np.cumsum(parts)

    def _get_scene_split(
        self, scenes: List[str], process_ind: int, total_processes: int
    ) -> List[str]:
        assert total_processes <= len(scenes), "More processes than scenes."
        inds = [0] + self._partition_inds(len(scenes), total_processes)
        return scenes[inds[process_ind] : inds[process_ind + 1]]

    def train_task_sampler_args(
        self, process_ind: int, total_processes: int
    ) -> Dict[str, Any]:
        all_train_scenes = ["FloorPlan{}".format(i) for i in range(1, 21)]
        return {
            "scenes": self._get_scene_split(
                all_train_scenes, process_ind, total_processes
            ),
            "object_type": self.OBJECT_TYPES,
        }

    def valid_task_sampler_args(
        self, process_ind: int, total_processes: int
    ) -> Dict[str, Any]:
        all_valid_scenes = ["FloorPlan{}".format(i) for i in range(21, 26)]
        return {
            "scenes": self._get_scene_split(
                all_valid_scenes, process_ind, total_processes
            ),
            "object_type": self.OBJECT_TYPES,
        }

    def test_task_sampler_args(
        self, process_ind: int, total_processes: int
    ) -> Dict[str, Any]:
        all_test_scenes = ["FloorPlan{}".format(i) for i in range(26, 31)]
        return {
            "scenes": self._get_scene_split(
                all_test_scenes, process_ind, total_processes
            ),
            "object_type": self.OBJECT_TYPES,
        }
