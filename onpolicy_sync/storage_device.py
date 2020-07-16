# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
import random
from collections import defaultdict
import typing
from typing import Union, List, Dict

import torch
import numpy as np


class RolloutStorage:
    """Class for storing rollout information for RL trainers."""

    def __init__(
        self,
        num_steps,
        num_processes,
        action_space,
        recurrent_hidden_state_size,
        num_recurrent_layers=1,
        flatten_separator='._AUTOFLATTEN_.'
    ):
        self.observations = {}

        self.recurrent_hidden_states = torch.zeros(
            num_steps + 1,
            num_recurrent_layers,
            num_processes,
            recurrent_hidden_state_size,
        )

        self.rewards = torch.zeros(num_steps, num_processes, 1)
        self.value_preds = torch.zeros(num_steps + 1, num_processes, 1)
        self.returns = torch.zeros(num_steps + 1, num_processes, 1)

        self.action_log_probs = torch.zeros(num_steps, num_processes, 1)
        if action_space.__class__.__name__ == "Discrete":
            action_shape = 1
        else:
            action_shape = action_space.shape[0]

        self.actions = torch.zeros(num_steps, num_processes, action_shape)
        self.prev_actions = torch.zeros(num_steps + 1, num_processes, action_shape)
        if action_space.__class__.__name__ == "Discrete":
            self.actions = self.actions.long()
            self.prev_actions = self.prev_actions.long()

        self.masks = torch.ones(num_steps + 1, num_processes, 1)

        self.flattened_spaces: Dict[str, List[str]] = dict()

        self.num_steps = num_steps
        self.step = 0
        self.flatten_separator = flatten_separator

        self.unnarrow_data: Dict[str, Union[int, torch.Tensor]] = defaultdict(dict)

    def to(self, device):
        for sensor in self.observations:
            self.observations[sensor] = self.observations[sensor].to(device)

        self.recurrent_hidden_states = self.recurrent_hidden_states.to(device)
        self.rewards = self.rewards.to(device)
        self.value_preds = self.value_preds.to(device)
        self.returns = self.returns.to(device)
        self.action_log_probs = self.action_log_probs.to(device)
        self.actions = self.actions.to(device)
        self.prev_actions = self.prev_actions.to(device)
        self.masks = self.masks.to(device)

    def flatten_spaces(self, observations: Dict[str, Union[torch.Tensor, Dict]]) -> Dict[str, torch.Tensor]:
        def recursive_flatten(obs: Dict[str, Union[torch.Tensor, Dict]], res: Dict[str, torch.Tensor],
                              prefix: str='', flatten_sep=self.flatten_separator) -> None:
            for sensor in obs:
                if not torch.is_tensor(obs[sensor]):
                    recursive_flatten(
                        obs[sensor], res, prefix=prefix + sensor + flatten_sep
                    )
                else:
                    sensor_name = prefix + sensor
                    res[sensor_name] = obs[sensor]
        flattened_obs = {}
        recursive_flatten(observations, flattened_obs)
        return flattened_obs

    def insert_initial_observations(self, observations: Dict[str, Union[torch.Tensor, Dict]], prefix: str='',
                                    path: List[str]=[], time_step: int=0):
        for sensor in observations:
            if not torch.is_tensor(observations[sensor]):
                self.insert_initial_observations(
                    observations[sensor],
                    prefix=prefix + sensor + self.flatten_separator,
                    path=path + [sensor],
                    time_step=time_step
                )
            else:
                sensor_name = prefix + sensor
                if sensor_name not in self.observations:
                    self.observations[sensor_name] = (
                        torch.zeros_like(observations[sensor])
                        .unsqueeze(0)
                        .repeat(
                            self.num_steps + 1,
                            *(1 for _ in range(len(observations[sensor].shape))),
                        )
                        .to(
                            "cpu"
                            if self.actions.get_device() < 0
                            else self.actions.get_device()
                        )
                    )

                    if len(path) > 0:
                        assert sensor_name not in self.flattened_spaces,\
                            "new flattened name {} already existing in flattened spaces".format(sensor_name)
                        self.flattened_spaces[sensor_name] = path + [sensor]

                self.observations[sensor_name][time_step].copy_(observations[sensor])

    def insert(
        self,
        observations,
        recurrent_hidden_states,
        actions,
        action_log_probs,
        value_preds,
        rewards,
        masks,
        *args,
    ):
        assert len(args) == 0

        # self.insert_observations(observations)
        self.insert_initial_observations(observations, time_step=self.step + 1)

        self.recurrent_hidden_states[self.step + 1].copy_(recurrent_hidden_states)
        self.actions[self.step].copy_(actions)
        self.prev_actions[self.step + 1].copy_(actions)
        self.action_log_probs[self.step].copy_(action_log_probs)
        self.value_preds[self.step].copy_(value_preds)
        self.rewards[self.step].copy_(rewards)
        self.masks[self.step + 1].copy_(masks)

        self.step = (self.step + 1) % self.num_steps

    def reshape(self, keep_list):
        for sensor in self.observations:
            self.observations[sensor] = self.observations[sensor][:, keep_list]
        self.recurrent_hidden_states = self.recurrent_hidden_states[:, :, keep_list]
        self.actions = self.actions[:, keep_list]
        self.prev_actions = self.prev_actions[:, keep_list]
        self.action_log_probs = self.action_log_probs[:, keep_list]
        self.value_preds = self.value_preds[:, keep_list]
        self.rewards = self.rewards[:, keep_list]
        self.masks = self.masks[:, keep_list]

    def narrow(self):
        assert len(self.unnarrow_data) == 0, "attempting to narrow narrowed rollouts"

        if self.step == 0:  # we're actually done
            return

        for sensor in self.observations:
            self.unnarrow_data["observations"][sensor] = self.observations[sensor]
            self.observations[sensor] = self.observations[sensor].narrow(0, 0, self.step + 1)

        self.unnarrow_data["recurrent_hidden_states"] = self.recurrent_hidden_states
        self.recurrent_hidden_states = self.recurrent_hidden_states.narrow(0, 0, self.step + 1)

        self.unnarrow_data["actions"] = self.actions
        self.actions = self.actions.narrow(0, 0, self.step)

        self.unnarrow_data["prev_actions"] = self.prev_actions
        self.prev_actions = self.prev_actions.narrow(0, 0, self.step + 1)

        self.unnarrow_data["action_log_probs"] = self.action_log_probs
        self.action_log_probs = self.action_log_probs.narrow(0, 0, self.step)

        self.unnarrow_data["value_preds"] = self.value_preds
        self.value_preds = self.value_preds.narrow(0, 0, self.step)

        self.unnarrow_data["rewards"] = self.rewards
        self.rewards = self.rewards.narrow(0, 0, self.step)

        self.unnarrow_data["masks"] = self.masks
        self.masks = self.masks.narrow(0, 0, self.step + 1)

        self.unnarrow_data["num_steps"] = self.num_steps
        self.num_steps = self.step

    def unnarrow(self):
        assert len(self.unnarrow_data) > 0, "attempting to unnarrow unnarrowed rollouts"

        for sensor in self.observations:
            self.observations[sensor] = self.unnarrow_data["observations"][sensor]
            del self.unnarrow_data["observations"][sensor]

        assert len(self.unnarrow_data["observations"]) == 0, "unnarrow_data contains observations {}".format(self.unnarrow_data["observations"])
        del self.unnarrow_data["observations"]

        self.recurrent_hidden_states = self.unnarrow_data["recurrent_hidden_states"]
        del self.unnarrow_data["recurrent_hidden_states"]

        self.actions = self.unnarrow_data["actions"]
        del self.unnarrow_data["actions"]

        self.prev_actions = self.unnarrow_data["prev_actions"]
        del self.unnarrow_data["prev_actions"]

        self.action_log_probs = self.unnarrow_data["action_log_probs"]
        del self.unnarrow_data["action_log_probs"]

        self.value_preds = self.unnarrow_data["value_preds"]
        del self.unnarrow_data["value_preds"]

        self.rewards = self.unnarrow_data["rewards"]
        del self.unnarrow_data["rewards"]

        self.masks = self.unnarrow_data["masks"]
        del self.unnarrow_data["masks"]

        self.num_steps = self.unnarrow_data["num_steps"]
        del self.unnarrow_data["num_steps"]

        assert len(self.unnarrow_data) == 0

    def after_update(self):
        assert self.step == 0, "wrong number of steps {} in rollouts storage with capacity {}".format(self.step, self.num_steps)

        for sensor in self.observations:
            self.observations[sensor][0].copy_(self.observations[sensor][-1])

        self.recurrent_hidden_states[0].copy_(self.recurrent_hidden_states[-1])
        self.masks[0].copy_(self.masks[-1])
        self.prev_actions[0].copy_(self.prev_actions[-1])

        if len(self.unnarrow_data) > 0:
            self.unnarrow()

    def compute_returns(self, next_value, use_gae, gamma, tau):
        if use_gae:
            self.value_preds[-1] = next_value
            gae = 0
            for step in reversed(range(self.rewards.size(0))):
                delta = (
                    self.rewards[step]
                    + gamma * self.value_preds[step + 1] * self.masks[step + 1]
                    - self.value_preds[step]
                )
                gae = delta + gamma * tau * self.masks[step + 1] * gae
                self.returns[step] = gae + self.value_preds[step]
        else:
            self.returns[-1] = next_value
            for step in reversed(range(self.rewards.size(0))):
                self.returns[step] = (
                    self.returns[step + 1] * gamma * self.masks[step + 1]
                    + self.rewards[step]
                )

    def recurrent_generator(self, advantages, num_mini_batch, device):
        normalized_advantages = (advantages - advantages.mean()) / (
            advantages.std() + 1e-5
        )

        num_processes = self.rewards.size(1)
        assert num_processes >= num_mini_batch, (
            "The number of processes ({}) "
            "must be greater than or equal to the number of "
            "mini batches ({}).".format(num_processes, num_mini_batch)
        )

        inds = np.round(
            np.linspace(0, num_processes, num_mini_batch + 1, endpoint=True)
        ).astype(np.int32)
        pairs = list(zip(inds[:-1], inds[1:]))
        random.shuffle(pairs)

        for start_ind, end_ind in pairs:
            observations_batch = defaultdict(list)

            recurrent_hidden_states_batch = []
            actions_batch = []
            prev_actions_batch = []
            value_preds_batch = []
            return_batch = []
            masks_batch = []
            old_action_log_probs_batch = []
            adv_targ = []
            norm_adv_targ = []

            for ind in range(start_ind, end_ind):
                for sensor in self.observations:
                    observations_batch[sensor].append(
                        self.observations[sensor][:-1, ind]
                    )

                recurrent_hidden_states_batch.append(
                    self.recurrent_hidden_states[0, :, ind]
                )

                actions_batch.append(self.actions[:, ind])
                prev_actions_batch.append(self.prev_actions[:-1, ind])
                value_preds_batch.append(self.value_preds[:-1, ind])
                return_batch.append(self.returns[:-1, ind])
                masks_batch.append(self.masks[:-1, ind])
                old_action_log_probs_batch.append(self.action_log_probs[:, ind])

                adv_targ.append(advantages[:, ind])
                norm_adv_targ.append(normalized_advantages[:, ind])

            T, N = self.num_steps, end_ind - start_ind

            # These are all tensors of size (T, N, -1)
            for sensor in observations_batch:
                # noinspection PyTypeChecker
                observations_batch[sensor] = torch.stack(observations_batch[sensor], 1).to(device)

            actions_batch = torch.stack(actions_batch, 1).to(device)
            prev_actions_batch = torch.stack(prev_actions_batch, 1).to(device)
            value_preds_batch = torch.stack(value_preds_batch, 1).to(device)
            return_batch = torch.stack(return_batch, 1).to(device)
            masks_batch = torch.stack(masks_batch, 1).to(device)
            old_action_log_probs_batch = torch.stack(old_action_log_probs_batch, 1).to(device)
            adv_targ = torch.stack(adv_targ, 1).to(device)
            norm_adv_targ = torch.stack(norm_adv_targ, 1).to(device)

            # States is just a (num_recurrent_layers, N, -1) tensor
            recurrent_hidden_states_batch = torch.stack(
                recurrent_hidden_states_batch, 1
            ).to(device)

            # Flatten the (T, N, ...) tensors to (T * N, ...)
            for sensor in observations_batch:
                # noinspection PyTypeChecker
                observations_batch[sensor] = self._flatten_helper(
                    t=T,
                    n=N,
                    tensor=typing.cast(torch.Tensor, observations_batch[sensor]),
                )

            actions_batch = self._flatten_helper(T, N, actions_batch)
            prev_actions_batch = self._flatten_helper(T, N, prev_actions_batch)
            value_preds_batch = self._flatten_helper(T, N, value_preds_batch)
            return_batch = self._flatten_helper(T, N, return_batch)
            masks_batch = self._flatten_helper(T, N, masks_batch)
            old_action_log_probs_batch = self._flatten_helper(
                T, N, old_action_log_probs_batch
            )
            adv_targ = self._flatten_helper(T, N, adv_targ)
            norm_adv_targ = self._flatten_helper(T, N, norm_adv_targ)

            yield {
                "observations": self.unflatten_spaces(observations_batch),
                "recurrent_hidden_states": recurrent_hidden_states_batch,
                "actions": actions_batch,
                "prev_actions": prev_actions_batch,
                "values": value_preds_batch,
                "returns": return_batch,
                "masks": masks_batch,
                "old_action_log_probs": old_action_log_probs_batch,
                "adv_targ": adv_targ,
                "norm_adv_targ": norm_adv_targ,
            }

    def unflatten_spaces(self, observations):
        def ddict2dict(d):
            for k, v in d.items():
                if isinstance(v, dict):
                    d[k] = ddict2dict(v)
            return dict(d)

        nested_dict = lambda: defaultdict(nested_dict)
        result = nested_dict()
        for name in observations:
            if name not in self.flattened_spaces:
                result[name] = observations[name]
            else:
                full_path = self.flattened_spaces[name]
                cur_dict = result
                for part in full_path[:-1]:
                    cur_dict = cur_dict[part]
                cur_dict[full_path[-1]] = observations[name]
        return ddict2dict(result)

    def pick_observation_step(self, step: int, device: Union[str, int, torch.device]) -> Dict[str, Union[Dict, torch.Tensor]]:
        observations_batch = {sensor: self.observations[sensor][step].to(device) for sensor in self.observations}
        return self.unflatten_spaces(observations_batch)

    @staticmethod
    def _flatten_helper(t: int, n: int, tensor: torch.Tensor) -> torch.Tensor:
        """Given a tensor of size (t, n, ..), flatten it to size (t*n, ...).

        Args:
            t: first dimension of tensor.
            n: second dimension of tensor.
            tensor: target tensor to be flattened.

        Returns:
            flattened tensor of size (t*n, ...)
        """
        return tensor.view(t * n, *tensor.size()[2:])
