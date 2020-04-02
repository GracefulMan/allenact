from typing import Dict, Any, List, Optional, Tuple, Union

import gym
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim.lr_scheduler import LambdaLR

from models.basic_models import LinearActorCritic
from onpolicy_sync.losses.imitation import Imitation
from rl_base.experiment_config import ExperimentConfig
from rl_base.sensor import SensorSuite, ExpertPolicySensor
from rl_base.task import TaskSampler
from rl_lighthouse.lighthouse_sensors import FactorialDesignCornerSensor
from rl_lighthouse.lighthouse_tasks import FindGoalLightHouseTaskSampler
from utils.experiment_utils import (
    Builder,
    PipelineStage,
    TrainingPipeline,
    LinearDecay,
    EarlyStoppingCriterion,
    ScalarMeanTracker,
)


class StopIfNearOptimal(EarlyStoppingCriterion):
    def __init__(self, optimal: float, deviation: float, gamma=0.9):
        self.optimal = optimal
        self.deviaion = deviation
        self.gamma = gamma
        self.running_mean = None

    def __call__(
        self,
        stage_steps: int,
        total_steps: int,
        training_metrics: ScalarMeanTracker,
        test_valid_metrics: List[Tuple[str, int, Union[float, np.ndarray]]],
    ) -> bool:
        sums = training_metrics.sums()
        counts = training_metrics.counts()

        k = "ep_length"
        if k in sums:
            count = counts[k]
            ep_length_ave = sums[k] / count

            if self.running_mean is None:
                self.running_mean = ep_length_ave
            else:
                self.running_mean = (1 - self.gamma ** count) * ep_length_ave + (
                    self.gamma ** count
                ) * self.running_mean

        if self.running_mean is None:
            return False
        return self.running_mean < self.optimal + self.deviaion


class LightHouseTwoDimDAggerExperimentConfig(ExperimentConfig):
    """Find goal in 2-dim lighthouse env.

    Training with DAgger.
    """

    WORLD_DIM = 2
    VIEW_RADIUS = 1
    EXPERT_VIEW_RADIUS = 1
    WORLD_RADIUS = 10
    DEGREE = -1
    MAX_STEPS = 1000

    SENSORS = [
        FactorialDesignCornerSensor(
            {"view_radius": VIEW_RADIUS, "world_dim": WORLD_DIM, "degree": DEGREE}
        ),
        ExpertPolicySensor(
            {
                "expert_args": {"expert_view_radius": EXPERT_VIEW_RADIUS},
                "nactions": 2 * WORLD_DIM,
            }
        ),
    ]

    @classmethod
    def tag(cls):
        return "LightHouseTwoDimDAgger"

    @classmethod
    def training_pipeline(cls, **kwargs):
        dagger_steps = int(1e5)
        imitation_steps = int(1e6) - dagger_steps
        lr = 1e-2
        num_mini_batch = 2
        update_repeats = 4
        num_steps = 128
        metric_accumulate_interval = cls.MAX_STEPS * 10  # Log every 10 max length tasks
        save_interval = 500000
        gamma = 0.99
        use_gae = True
        gae_lambda = 1.0
        max_grad_norm = 0.5

        return TrainingPipeline(
            save_interval=save_interval,
            metric_accumulate_interval=metric_accumulate_interval,
            optimizer_builder=Builder(optim.Adam, dict(lr=lr)),
            num_mini_batch=num_mini_batch,
            update_repeats=update_repeats,
            max_grad_norm=max_grad_norm,
            num_steps=num_steps,
            named_losses={"imitation_loss": Builder(Imitation,),},
            gamma=gamma,
            use_gae=use_gae,
            gae_lambda=gae_lambda,
            advance_scene_rollout_period=None,
            pipeline_stages=[
                PipelineStage(
                    loss_names=["imitation_loss"],
                    early_stopping_criterion=StopIfNearOptimal(
                        optimal=50, deviation=10
                    ),
                    max_stage_steps=imitation_steps,
                ),
            ],
            lr_scheduler_builder=Builder(
                LambdaLR, {"lr_lambda": LinearDecay(steps=dagger_steps)}
            ),
        )

    @classmethod
    def machine_params(cls, mode="train", **kwargs):
        if mode == "train":
            nprocesses = 10 if not torch.cuda.is_available() else 20
            gpu_ids = [] if not torch.cuda.is_available() else [0]
        elif mode == "valid":
            nprocesses = 0
            gpu_ids = [] if not torch.cuda.is_available() else [1]
        elif mode == "test":
            nprocesses = 1
            gpu_ids = [] if not torch.cuda.is_available() else [0]
        else:
            raise NotImplementedError("mode must be 'train', 'valid', or 'test'.")

        return {"nprocesses": nprocesses, "gpu_ids": gpu_ids}

    @classmethod
    def create_model(cls, **kwargs) -> nn.Module:
        return LinearActorCritic(
            input_key=cls.SENSORS[0]._get_uuid(),
            action_space=gym.spaces.Discrete(2 * cls.WORLD_DIM),
            observation_space=SensorSuite(cls.SENSORS).observation_spaces,
        )

    @staticmethod
    def make_sampler_fn(**kwargs) -> TaskSampler:
        return FindGoalLightHouseTaskSampler(**kwargs)

    def train_task_sampler_args(
        self,
        process_ind: int,
        total_processes: int,
        devices: Optional[List[int]] = None,
        seeds: Optional[List[int]] = None,
        deterministic_cudnn: bool = False,
    ) -> Dict[str, Any]:
        return {
            "world_dim": self.WORLD_DIM,
            "world_radius": self.WORLD_RADIUS,
            "max_steps": self.MAX_STEPS,
            "sensors": self.SENSORS,
            "action_space": gym.spaces.Discrete(2 * self.WORLD_DIM),
            "seed": seeds[process_ind] if seeds is not None else None,
        }

    def valid_task_sampler_args(
        self,
        process_ind: int,
        total_processes: int,
        devices: Optional[List[int]],
        seeds: Optional[List[int]] = None,
        deterministic_cudnn: bool = False,
    ) -> Dict[str, Any]:
        return self.train_task_sampler_args(
            process_ind=process_ind,
            total_processes=total_processes,
            devices=devices,
            seeds=seeds,
            deterministic_cudnn=deterministic_cudnn,
        )

    def test_task_sampler_args(
        self,
        process_ind: int,
        total_processes: int,
        devices: Optional[List[int]],
        seeds: Optional[List[int]] = None,
        deterministic_cudnn: bool = False,
    ) -> Dict[str, Any]:
        return self.train_task_sampler_args(
            process_ind=process_ind,
            total_processes=total_processes,
            devices=devices,
            seeds=seeds,
            deterministic_cudnn=deterministic_cudnn,
        )
