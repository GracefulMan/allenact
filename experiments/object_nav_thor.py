from math import ceil
from typing import Dict, Any, List, Optional

import gym
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from onpolicy_sync.losses.ppo import PPOConfig
from models.object_nav_models import ObjectNavBaselineActorCritic
from rl_ai2thor.ai2thor_sensors import RGBSensorThor, GoalObjectTypeThorSensor
from rl_ai2thor.object_nav.task_samplers import ObjectNavTaskSampler
from rl_ai2thor.object_nav.tasks import ObjectNavTask
from utils.experiment_utils import LinearDecay, Builder, PipelineStage, TrainingPipeline
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
    VALID_SCENES = [
        "FloorPlan1_physics"
    ]  # ["FloorPlan{}_physics".format(i) for i in range(21, 26)]
    TEST_SCENES = ["FloorPlan{}_physics".format(i) for i in range(26, 31)]

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

    VALID_SAMPLES_IN_SCENE = 5

    @classmethod
    def tag(cls):
        return "ObjectNav"

    @classmethod
    def training_pipeline(cls, **kwargs):
        dagger_steps = int(3e4)
        ppo_steps = int(3e4)
        ppo_steps2 = int(1e6)
        lr = 2.5e-4
        num_mini_batch = 1
        update_repeats = 3
        num_steps = 16
        log_interval = 2 * num_steps * cls.machine_params("train")["nprocesses"]
        save_interval = 2 * log_interval
        gamma = 0.99
        use_gae = True
        gae_lambda = 1.0
        max_grad_norm = 0.5
        return TrainingPipeline(
            save_interval=save_interval,
            log_interval=log_interval,
            optimizer=Builder(optim.Adam, dict(lr=lr)),
            num_mini_batch=num_mini_batch,
            update_repeats=update_repeats,
            num_steps=num_steps,
            named_losses={
                "imitation_loss": Builder(Imitation,),
                "ppo_loss": Builder(PPO, dict(), default=PPOConfig,),
            },
            gamma=gamma,
            use_gae=use_gae,
            gae_lambda=gae_lambda,
            max_grad_norm=max_grad_norm,
            pipeline_stages=[
                PipelineStage(
                    loss_names=["imitation_loss", "ppo_loss"],
                    teacher_forcing=LinearDecay(
                        startp=1.0, endp=0.0, steps=dagger_steps,
                    ),
                    end_criterion=dagger_steps,
                ),
                PipelineStage(
                    loss_names=["ppo_loss", "imitation_loss"], end_criterion=ppo_steps
                ),
                PipelineStage(loss_names=["ppo_loss"], end_criterion=ppo_steps2,),
            ],
        )

    @classmethod
    def machine_params(cls, mode="train", **kwargs):
        if mode == "train":
            nprocesses = 3
            gpu_ids = [] if not torch.cuda.is_available() else [0]
        elif mode in ["valid", "test"]:
            nprocesses = 0
            gpu_ids = [] if not torch.cuda.is_available() else [1]
        else:
            raise NotImplementedError("mode must be 'train', 'valid', or 'test'.")

        return {"nprocesses": nprocesses, "gpu_ids": gpu_ids}

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
        self,
        scenes: List[str],
        process_ind: int,
        total_processes: int,
        seeds: Optional[List[int]] = None,
        deterministic_cudnn: bool = False,
    ) -> Dict[str, Any]:
        if total_processes > len(scenes):  # oversample some scenes -> bias
            if total_processes % len(scenes) != 0:
                print(
                    "Warning: oversampling some of the scenes to feed all processes."
                    " You can avoid this by setting a number of workers divisible by the number of scenes"
                )
            scenes = scenes * int(ceil(total_processes / len(scenes)))
            scenes = scenes[: total_processes * (len(scenes) // total_processes)]
        else:
            if len(scenes) % total_processes != 0:
                print(
                    "Warning: oversampling some of the scenes to feed all processes."
                    " You can avoid this by setting a number of workers divisor of the number of scenes"
                )
        inds = self._partition_inds(len(scenes), total_processes)

        return {
            "scenes": scenes[inds[process_ind] : inds[process_ind + 1]],
            "object_types": self.OBJECT_TYPES,
            "env_args": self.ENV_ARGS,
            "max_steps": self.MAX_STEPS,
            "sensors": self.SENSORS,
            "action_space": gym.spaces.Discrete(len(ObjectNavTask.action_names())),
            "seed": seeds[process_ind] if seeds is not None else None,
            "deterministic_cudnn": deterministic_cudnn,
        }

    def train_task_sampler_args(
        self,
        process_ind: int,
        total_processes: int,
        devices: Optional[List[int]] = None,
        seeds: Optional[List[int]] = None,
        deterministic_cudnn: bool = False,
    ) -> Dict[str, Any]:
        res = self._get_sampler_args_for_scene_split(
            self.TRAIN_SCENES,
            process_ind,
            total_processes,
            seeds=seeds,
            deterministic_cudnn=deterministic_cudnn,
        )
        res["scene_period"] = self.SCENE_PERIOD
        res["env_args"]["x_display"] = "0.%d" % devices[0] if len(devices) > 0 else None
        return res

    def valid_task_sampler_args(
        self,
        process_ind: int,
        total_processes: int,
        devices: Optional[List[int]],
        seeds: Optional[List[int]] = None,
        deterministic_cudnn: bool = False,
    ) -> Dict[str, Any]:
        res = self._get_sampler_args_for_scene_split(
            self.VALID_SCENES,
            process_ind,
            total_processes,
            seeds=seeds,
            deterministic_cudnn=deterministic_cudnn,
        )
        res["scene_period"] = self.VALID_SAMPLES_IN_SCENE
        res["max_tasks"] = self.VALID_SAMPLES_IN_SCENE * len(res["scenes"])
        res["env_args"]["x_display"] = "0.%d" % devices[0] if len(devices) > 0 else None
        return res

    def test_task_sampler_args(
        self,
        process_ind: int,
        total_processes: int,
        devices: Optional[List[int]],
        seeds: Optional[List[int]] = None,
        deterministic_cudnn: bool = False,
    ) -> Dict[str, Any]:
        res = self._get_sampler_args_for_scene_split(
            self.TEST_SCENES,
            process_ind,
            total_processes,
            seeds=seeds,
            deterministic_cudnn=deterministic_cudnn,
        )
        res["env_args"]["x_display"] = "0.%d" % devices[0] if len(devices) > 0 else None
        return res
