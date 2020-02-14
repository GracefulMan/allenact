from typing import List, Optional, Union

from rl_habitat.habitat_environment import HabitatEnvironment
import gym
from habitat.config import Config

from rl_base.sensor import Sensor
from rl_base.task import TaskSampler
from rl_habitat.habitat_tasks import PointNavTask


class PointNavTaskSampler(TaskSampler):
    def __init__(
        self,
        env_config: Config,
        sensors: List[Sensor],
        max_steps: int,
        action_space: gym.Space,
        distance_to_goal: float,
        *args,
        **kwargs
    ) -> None:
        self.grid_size = 0.25
        self.env: Optional[HabitatEnvironment] = None
        self.sensors = sensors
        self.max_steps = max_steps
        self._action_space = action_space
        self.env_config = env_config
        self.distance_to_goal = distance_to_goal

        self._last_sampled_task: Optional[PointNavTask] = None

    def _create_environment(self) -> HabitatEnvironment:
        self.env_config.freeze()
        env = HabitatEnvironment(
            config=self.env_config,
        )
        return env

    @property
    def __len__(self) -> Union[int, float]:
        """
        @return: Number of total tasks remaining that can be sampled. Can be float('inf').
        """
        return float("inf")

    @property
    def total_unique(self) -> Union[int, float, None]:
        return None

    @property
    def last_sampled_task(self) -> Optional[PointNavTask]:
        return self._last_sampled_task

    def close(self) -> None:
        if self.env is not None:
            self.env.stop()

    @property
    def all_observation_spaces_equal(self) -> bool:
        """
        @return: True if all Tasks that can be sampled by this sampler have the
            same observation space. Otherwise False.
        """
        return True

    def next_task(self, force_advance_scene=False) -> PointNavTask:

        if self.env is not None:
            self.env.reset()
        else:
            self.env = self._create_environment()
            self.env.reset()
            # self.env.start() # We don't need this here because rl_habitat does not need to start
        ep_info = self.env.get_current_episode()
        target = ep_info.goals[0].position

        task_info = {
            "target": target,
            "distance_to_goal": self.distance_to_goal,
            "actions": []
        }

        self._last_sampled_task = PointNavTask(
            env=self.env,
            sensors=self.sensors,
            task_info=task_info,
            max_steps=self.max_steps,
            action_space=self._action_space,
        )
        return self._last_sampled_task

    def reset(self):
        print("Don't have to reset rl_habitat task sampler")
        # self.scene_counter = 0
        # self.scene_order = list(range(len(self.scenes)))
        # random.shuffle(self.scene_order)
        # self.scene_id = 0
        # self.max_tasks = self.reset_tasks

    def set_seed(self, seed: int):
        self.seed = seed
        if seed is not None:
            set_seed(seed)
