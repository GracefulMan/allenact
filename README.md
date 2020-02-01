# EmbodiedRL

EmbodiedRL is a library designed for research in embodied reinforcement learning with
a focus on modularity, flexibility, and low cognitive overhead. This work builds upon
the [pytorch-a2c-ppo-acktr](https://github.com/ikostrikov/pytorch-a2c-ppo-acktr-gail) 
library of Ilya Kostrikov and uses some data structures from FAIR's 
[habitat-api](https://github.com/facebookresearch/habitat-api).

Currently, two RL algorithms are implemented

* Advantage Actor Critic (A2C) - synchronized [A3C](https://arxiv.org/pdf/1602.01783v1.pdf)
* [Proximal Policy Optimization (PPO)](https://arxiv.org/pdf/1707.06347.pdf)

## Table of contents

1. [Why embodied-rl?](#why)
1. [Installation](#installation)
1. [Contributions](#contributions)
1. [Citiation](#citation)

## Why `embodied-rl`?

There are an increasingly 
[large collection](https://winderresearch.com/a-comparison-of-reinforcement-learning-frameworks-dopamine-rllib-keras-rl-coach-trfl-tensorforce-coach-and-more/) 
of deep reinforcement learning packages and so it is natural to question why we introduce another framework
reproducing many of the same algorithms and ideas. After performing a survey of existing frameworks we
could not find a package delivering all of the following features, each of which we considered critical.

1. *Decoupled tasks and environments*: a large portion of existing RL frameworks organize themselves using abstractions 
   from the OpenAI gym. These abstractions center around the `Env` class which encapsulates an agent's environment,
   how it interacts with that environment, and the rewards received by the agent when taking actions. This 
   is an excellent abstraction when an environment is intimiately tied to a single task (e.g. with Atari games
   where the environment is a single game with a single goal). In embodied AI research, however, it is important to be 
   able to define many tasks for a single environment; for instance, the [AI2-THOR](https://ai2thor.allenai.org/)
   environment has been used with tasks such as
   
    * [semantic/object navigation](https://arxiv.org/abs/1810.06543),
    * [interactive question answering](https://arxiv.org/abs/1712.03316),
    * [multi-agent furniture lifting](https://prior.allenai.org/projects/two-body-problem), and
    * [adversarial hide-and-seek](https://arxiv.org/abs/1912.08195).
   
    We have designed `embodied-rl` to easily support a wide variety of tasks designed for individual environments.

1. *First-class pytorch support*: while many well-developed libraries exist for reinforcement learning in 
   tensorflow we prefer the abstractions and design provided by pytorch.
1. *Configuration as code*: defining experiments using yaml configuation files is a perplexing standard. We have found
   such configuration files to be restrictive, brittle, and difficult to debug. In `embodied-rl` experiments are 
   defined using python classes, if you know how to extend an abstract python class then you know how to define an
   experiment.
1. *Type checking and documentation*: we have put significant effort into providing extensive documentation and type
   annotations throughout our codebase.


## Installation

Begin by cloning this repository to your local machine and moving into the top-level directory

```bash
git clone git@github.com:allenai/embodied-rl.git
cd embodied-rl
```

This library has been tested only in python 3.6, the following assumes you have a working
version of python 3.6 installed locally. In order to install requirements we recommend
using [pipenv](https://pipenv.kennethreitz.org/en/latest/) but also include instructions if
you would prefer to install things directly using pip.

### Installing requirements with `pipenv` (*recommended*)

If you have already installed [pipenv](https://pipenv.kennethreitz.org/en/latest/), you may
run the following to install all requirements.

```bash
pipenv install --skip-lock --dev
```

### Installing requirements with `pip`

Note: *do not* run the following if you have already installed requirements with `pipenv`
as above. If you prefer using `pip`, you may install all requirements as follows

```bash
pip install -r requirements.txt
```

Depending on your machine configuration, you may need to use `pip3` instead of `pip` in the
above.


## Contributions

We in the Perceptural Reasoning and Interaction Research (PRIOR) group at the
 Allen Institute for AI (AI2, @allenai) welcome contributions from the greater community. If
 you would like to make such a contributions we recommend first submitting an 
 [issue](https://github.com/allenai/embodied-rl/issues) describing your proposed improvement.
 Doing so can ensure we can validate your suggestions before you spend a great deal of time
 upon them. Small (or validated) improvements and bug fixes should be made via a pull request
 from your fork of this repository.
 
All code in this repository is subject to formatting, documentation, and type-annotation
guidelines. For more details, please see the our [contribution guidelines](./CONTRIBUTING.md).   
  
## Citation

If you use this work, please cite:

```text
@misc{embodied-rl,
  author = {Jordi Salvador and Luca Weihs},
  title = {A Python Package for Embodied Reinforcement Learning},
  year = {2020},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/allenai/embodied-rl}},
}

```
