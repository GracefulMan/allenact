import math
from typing import Dict, Any, Union, Callable, Optional


def _pos_to_str(pos: Dict[str, float]) -> str:
    return "_".join([str(pos["x"]), str(pos["y"]), str(pos["z"])])


def _str_to_pos(s: str) -> Dict[str, float]:
    split = s.split("_")
    return {"x": float(split[0]), "y": float(split[1]), "z": float(split[2])}


def get_distance(
    cache: Dict[str, Any], pos: Dict[str, float], target: Dict[str, float]
) -> float:
    pos = {
        "x": 0.25 * math.ceil(pos["x"] / 0.25),
        "y": pos["y"],
        "z": 0.25 * math.ceil(pos["z"] / 0.25),
    }
    sp = _get_shortest_path_distance_from_cache(cache, pos, target)
    if sp == -1.0:
        pos = {
            "x": 0.25 * math.floor(pos["x"] / 0.25),
            "y": pos["y"],
            "z": 0.25 * math.ceil(pos["z"] / 0.25),
        }
        sp = _get_shortest_path_distance_from_cache(cache, pos, target)
    if sp == -1.0:
        pos = {
            "x": 0.25 * math.ceil(pos["x"] / 0.25),
            "y": pos["y"],
            "z": 0.25 * math.floor(pos["z"] / 0.25),
        }
        sp = _get_shortest_path_distance_from_cache(cache, pos, target)
    if sp == -1.0:
        pos = {
            "x": 0.25 * math.floor(pos["x"] / 0.25),
            "y": pos["y"],
            "z": 0.25 * math.floor(pos["z"] / 0.25),
        }
        sp = _get_shortest_path_distance_from_cache(cache, pos, target)
    if sp == -1.0:
        pos = find_nearest_point_in_cache(cache, pos)
        sp = _get_shortest_path_distance_from_cache(cache, pos, target)
    if sp == -1.0:
        target = find_nearest_point_in_cache(cache, target)
        sp = _get_shortest_path_distance_from_cache(cache, pos, target)
    if sp == -1.0:
        print("Your cache is incomplete!")
        exit()
    return sp


def get_distance_to_object(
    cache: Dict[str, Any], pos: Dict[str, float], target_class: str
) -> float:

    dists = []
    weights = []
    for rounder_func_0 in [math.ceil, math.floor]:
        for rounder_func_1 in [math.ceil, math.floor]:
            rounded_pos = {
                "x": 0.25 * rounder_func_0(pos["x"] / 0.25),
                "y": pos["y"],
                "z": 0.25 * rounder_func_1(pos["z"] / 0.25),
            }
            dist = _get_shortest_path_distance_to_object_from_cache(
                cache, rounded_pos, target_class
            )
            if dist >= 0:
                dists.append(dist)
                weights.append(
                    1.0
                    / (
                        math.sqrt(
                            (pos["x"] - rounded_pos["x"]) ** 2
                            + (pos["z"] - rounded_pos["z"]) ** 2
                        )
                        + 1e6
                    )
                )

    if len(dists) == 0:
        raise RuntimeError("Your cache is incomplete!")

    total_weight = sum(weights)
    weights = [w / total_weight for w in weights]

    return sum(d * w for d, w in zip(dists, weights))


def _get_shortest_path_distance_from_cache(
    cache: Dict[str, Any], position: Dict[str, float], target: Dict[str, float]
) -> float:
    try:
        return cache[_pos_to_str(position)][_pos_to_str(target)]["distance"]
    except:
        return -1.0


def _get_shortest_path_distance_to_object_from_cache(
    cache: Dict[str, Any], position: Dict[str, float], target_class: str
) -> float:
    try:
        return cache[_pos_to_str(position)][target_class]["distance"]
    except:
        return -1.0


def find_nearest_point_in_cache(
    cache: Dict[str, Any], point: Dict[str, float]
) -> Dict[str, float]:
    best_delta = float("inf")
    closest_point: Dict[str, float] = {}
    for p in cache:
        pos = _str_to_pos(p)
        delta = (
            abs(point["x"] - pos["x"])
            + abs(point["y"] - pos["y"])
            + abs(point["z"] - pos["z"])
        )
        if delta < best_delta:
            best_delta = delta
            closest_point = pos
    return closest_point


class DynamicDistanceCache(object):
    def __init__(self, rounding: Optional[int] = None):
        self.cache: Dict[str, Any] = {}
        self.rounding = rounding

    def find_distance(
        self,
        position: Dict[str, Any],
        target: Union[Dict[str, Any], str],
        native_distance_function: Callable[
            [Dict[str, Any], Union[Dict[str, Any], str]], float
        ],
    ) -> float:
        # Convert the position to its rounded string representation
        position_str = self._pos_to_str(position)
        # If the target is also a position, convert it to its rounded string representation
        if isinstance(target, str):
            target_str = target
        else:
            target_str = self._pos_to_str(target)

        if position_str not in self.cache:
            self.cache[position_str] = {}
        if target_str not in self.cache[position_str]:
            self.cache[position_str][target_str] = native_distance_function(
                position, target
            )
        return self.cache[position_str][target_str]

    def invalidate(self):
        self.cache = []

    def _pos_to_str(self, pos: Dict[str, Any]) -> str:
        if self.rounding:
            pos = {k: round(v, self.rounding) for k, v in pos.items()}
        return str(pos)
