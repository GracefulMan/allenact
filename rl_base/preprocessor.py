from typing import Dict, Any, List
from collections import OrderedDict
import abc

import gym
from gym.spaces import Dict as SpaceDict
import networkx as nx


class Preprocessor(abc.ABC):
    """Represents a preprocessor that transforms data from a sensor or another
    preprocessor to the input of agents or other preprocessors. The user of
    this class needs to implement the process method and the user is also
    required to set the below attributes:

    Attributes:
        config: configuration information for the preprocessor.
        uuid: universally unique id.
        observation_space: ``gym.Space`` object corresponding to processed observation spaces.
    """

    config: Dict[str, Any]
    input_uuids: List[str]
    uuid: str
    observation_space: gym.Space

    def __init__(self, config: Dict[str, Any], *args: Any, **kwargs: Any) -> None:
        self.config = config
        self.uuid = self._get_uuid()
        self.input_uuids = self._get_input_uuids()

    @abc.abstractmethod
    def _get_uuid(self, *args: Any, **kwargs: Any) -> str:
        """The unique ID of the preprocessor.

        @param args: extra args.
        @param kwargs: extra kwargs.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _get_input_uuids(self, *args: Any, **kwargs: Any) -> List[str]:
        """The unique IDs of the input sensors and preprocessors.

        @param args: extra args.
        @param kwargs: extra kwargs.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _get_observation_space(self) -> gym.Space:
        """The output observation space of the sensor."""
        raise NotImplementedError()

    @abc.abstractmethod
    def process(self, obs: Dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        """Returns processed observations from sensors or other preprocessors.

        @param obs: dict with available observations and processed observations.
        @return: processed observation.
        """
        raise NotImplementedError()


class PreprocessorGraph:
    """Represents a graph of preprocessors, with each preprocessor being
    identified through a unique id.

    Attributes:
        preprocessors: list containing preprocessors with required input uuids, output uuid of each
            sensor must be unique.
    """

    preprocessors: Dict[str, Preprocessor]
    observation_spaces: SpaceDict

    def __init__(self, preprocessors: List[Preprocessor],) -> None:
        """
        @param preprocessors: the preprocessors that will be included in the graph.
        """
        self.preprocessors = OrderedDict()
        spaces: OrderedDict[str, gym.Space] = OrderedDict()
        for preprocessor in preprocessors:
            assert (
                preprocessor.uuid not in self.preprocessors
            ), "'{}' is duplicated preprocessor uuid".format(preprocessor.uuid)
            self.preprocessors[preprocessor.uuid] = preprocessor
            spaces[preprocessor.uuid] = preprocessor.observation_space
        self.observation_spaces = SpaceDict(spaces=spaces)

        g = nx.DiGraph()
        for k in self.preprocessors:
            g.add_node(k)
        for k in self.preprocessors:
            for j in self.preprocessors[k].input_uuids:
                if j not in g:
                    g.add_node(j)
                g.add_edge(k, j)
        assert nx.is_directed_acyclic_graph(
            g
        ), "preprocessors do not form a direct acyclic graph"

        # ensure dependencies are precomputed
        self.compute_order = [n for n in nx.dfs_postorder_nodes(g)]

    def get(self, uuid: str) -> Preprocessor:
        """Return preprocessor with the given `uuid`.

        @param uuid: the unique id of the preprocessor
        @return: the preprocessor with unique id `uuid`.
        """
        return self.preprocessors[uuid]

    def get_observations(
        self, obs: Dict[str, Any], *args: Any, **kwargs: Any
    ) -> Dict[str, Any]:
        """
        @return: collect observations processed from all sensors and return it packaged inside a Dict.
        """

        for uuid in self.compute_order:
            if uuid not in obs:
                obs[uuid] = self.preprocessors[uuid].process(obs)

        return obs


class ObservationSet:
    """Represents a list of source_ids, corresponding to sensors and
    preprocessors, with each source being identified through a unique id.

    Attributes:
        source_ids: list containing sensor and preprocessor ids for the environment, uuid of each
            source must be unique.
        graph: computation graph for preprocessors
    """

    source_ids: List[str]
    graph: PreprocessorGraph

    def __init__(
        self, source_ids: List[str], all_preprocessors: List[Preprocessor],
    ) -> None:
        """
        @param source_ids: the sensors and preprocessors that will be included in the set.
        @param all_preprocessors: the entire list of preprocessors to be executed
        """

        self.graph = PreprocessorGraph(all_preprocessors)

        self.source_ids = source_ids
        assert len(set(self.source_ids)) == len(
            self.source_ids
        ), "No duplicated uuids allowed"

    def get(self, uuid: str) -> Preprocessor:
        """Return preprocessor with the given `uuid`.

        @param uuid: the unique id of the preprocessor
        @return: the preprocessor with unique id `uuid`.
        """
        return self.graph.get(uuid)

    def get_observations(
        self, obs: Dict[str, Any], *args: Any, **kwargs: Any
    ) -> Dict[str, Any]:
        """
        @return: collect observations from all sources and return them packaged inside a Dict.
        """
        obs = self.graph.get_observations(obs)
        return OrderedDict([(k, obs[k]) for k in self.source_ids])
