from typing import Dict, Any, List, Optional
from math import ceil

import gym
import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim.lr_scheduler import LambdaLR
import numpy as np
import glob

from onpolicy_sync.losses.ppo import PPOConfig
from onpolicy_sync.losses import PPO
from rl_robothor.robothor_tasks import PointNavTask
from rl_robothor.robothor_sensors import GPSCompassSensorRoboThor
from rl_ai2thor.ai2thor_sensors import RGBSensorThor
from utils.experiment_utils import Builder, PipelineStage, TrainingPipeline, LinearDecay
from projects.pointnav_baselines.models.point_nav_models import (
    PointNavActorCriticSimpleConvRNN,
)
from projects.pointnav_baselines.experiments.ithor.pointnav_ithor_base import (
    PointNaviThorBaseConfig,
)


class PointNaviThorRGBPPOExperimentConfig(PointNaviThorBaseConfig):
    """An Point Navigation experiment configuration in iThor with RGB input."""

    def __init__(self):
        super().__init__()
        self.SENSORS = [
            RGBSensorThor(
                height=self.SCREEN_SIZE,
                width=self.SCREEN_SIZE,
                use_resnet_normalization=True,
                uuid="rgb_lowres",
            ),
            GPSCompassSensorRoboThor(),
        ]

        self.PREPROCESSORS = []

        self.OBSERVATIONS = [
            "rgb_lowres",
            "target_coordinates_ind",
        ]

    @classmethod
    def tag(cls):
        return "Pointnav-iTHOR-RGB-SimpleConv-DDPPO"

    @classmethod
    def training_pipeline(cls, **kwargs):
        ppo_steps = int(75000000)
        lr = 3e-4
        num_mini_batch = 1
        update_repeats = 3
        num_steps = 30
        save_interval = 5000000
        log_interval = 10000
        gamma = 0.99
        use_gae = True
        gae_lambda = 0.95
        max_grad_norm = 0.5
        return TrainingPipeline(
            save_interval=save_interval,
            metric_accumulate_interval=log_interval,
            optimizer_builder=Builder(optim.Adam, dict(lr=lr)),
            num_mini_batch=num_mini_batch,
            update_repeats=update_repeats,
            max_grad_norm=max_grad_norm,
            num_steps=num_steps,
            named_losses={"ppo_loss": Builder(PPO, kwargs={}, default=PPOConfig,)},
            gamma=gamma,
            use_gae=use_gae,
            gae_lambda=gae_lambda,
            advance_scene_rollout_period=cls.ADVANCE_SCENE_ROLLOUT_PERIOD,
            pipeline_stages=[
                PipelineStage(loss_names=["ppo_loss"], max_stage_steps=ppo_steps)
            ],
            lr_scheduler_builder=Builder(
                LambdaLR, {"lr_lambda": LinearDecay(steps=ppo_steps)}
            ),
        )

    @classmethod
    def create_model(cls, **kwargs) -> nn.Module:
        return PointNavActorCriticSimpleConvRNN(
            action_space=gym.spaces.Discrete(len(PointNavTask.class_action_names())),
            observation_space=kwargs["observation_set"].observation_spaces,
            goal_sensor_uuid="target_coordinates_ind",
            hidden_size=512,
            embed_coordinates=False,
            coordinate_dims=2,
            num_rnn_layers=1,
            rnn_type="GRU",
        )
