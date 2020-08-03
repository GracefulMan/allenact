import gym
import habitat
import torch.nn as nn

<<<<<<< HEAD:projects/pointnav_baselines/experiments/habitat/pointnav_habitat_rgb_deterministic_pretrainedresnextGRU_ppo.py
from projects.pointnav_baselines.models.point_nav_models import PointNavActorCriticResNeXTPreTrained
=======
from experiments.pointnav_habitat_base import PointNavHabitatBaseExperimentConfig
from models.point_nav_models import PointNavActorCriticResNeXTPreTrained
>>>>>>> de752be39b1a7d9a4e4dc432293e3a12387385d2:experiments/pointnav_habitat_rgb_deterministic_pretrainedresnextGRU_ppo.py
from rl_base.sensor import SensorSuite
from rl_habitat.habitat_sensors import RGBSensorHabitat, TargetCoordinatesSensorHabitat
from rl_habitat.habitat_tasks import PointNavTask
from rl_habitat.habitat_utils import construct_env_configs
<<<<<<< HEAD:projects/pointnav_baselines/experiments/habitat/pointnav_habitat_rgb_deterministic_pretrainedresnextGRU_ppo.py
from projects.pointnav_baselines.experiments.habitat.pointnav_habitat_base import PointNavHabitatBaseExperimentConfig
=======
>>>>>>> de752be39b1a7d9a4e4dc432293e3a12387385d2:experiments/pointnav_habitat_rgb_deterministic_pretrainedresnextGRU_ppo.py


class PointNavHabitatRGBDeterministicPretrainedResNext101PPOExperimentConfig(
    PointNavHabitatBaseExperimentConfig
):
    """A Point Navigation experiment configuraqtion in Habitat."""

    SENSORS = [
        RGBSensorHabitat(
            **{
                "height": PointNavHabitatBaseExperimentConfig.SCREEN_SIZE,
                "width": PointNavHabitatBaseExperimentConfig.SCREEN_SIZE,
                "use_resnet_normalization": True,
            }
        ),
        TargetCoordinatesSensorHabitat(**{"coordinate_dims": 2}),
    ]

    PREPROCESSORS = []

    OBSERVATIONS = [
        "rgb",
        "target_coordinates_ind",
    ]

    CONFIG = PointNavHabitatBaseExperimentConfig.CONFIG.clone()
    CONFIG.SIMULATOR.AGENT_0.SENSORS = ["RGB_SENSOR"]

    TRAIN_CONFIGS = construct_env_configs(CONFIG)

    @classmethod
    def train_config(cls, process_ind: int) -> habitat.Config:
        return cls.TRAIN_CONFIGS[process_ind]

    @classmethod
    def create_model(cls, **kwargs) -> nn.Module:
        return PointNavActorCriticResNeXTPreTrained(
            action_space=gym.spaces.Discrete(len(PointNavTask.class_action_names())),
            observation_space=SensorSuite(cls.SENSORS).observation_spaces,
            goal_sensor_uuid="target_coordinates_ind",
            hidden_size=512,
            embed_coordinates=False,
            coordinate_dims=2,
            num_rnn_layers=1,
            rnn_type="GRU",
        )
