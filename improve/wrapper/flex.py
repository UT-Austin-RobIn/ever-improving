from __future__ import annotations
from tqdm import tqdm
import collections

import os
from datetime import datetime

import gym
import gymnasium as gym
import h5py
import hydra
import improve
import improve.config.resolver
import improve.wrapper.dict_util as du
import improve.wrapper.residualrl as rrl
import numpy as np
from gymnasium.core import Wrapper
from omegaconf import OmegaConf
from omegaconf import OmegaConf as OC

HOME = os.path.expanduser("~")
DATA_DIR = os.path.join(HOME, "datasets", "simpler")


class HDF5LoggerWrapper(Wrapper):

    def __init__(self, env, rootdir=DATA_DIR):
        super(HDF5LoggerWrapper, self).__init__(env)

        self.rootdir = rootdir
        self.file = None
        self.dataset_info_group = None
        self.episode_group = None
        self.step_group = None
        self.counter = 0

    def reset(self, **kwargs):
        
        os.makedirs(self.rootdir, exist_ok=True)  # Ensure the directory exists
        
        # create the dataset file if it does not exist
        if os.path.exists(os.path.join(self.rootdir, "dataset.h5")):
            self.file = h5py.File(os.path.join(self.rootdir, "dataset.h5"), "a", libver='latest')
        else:
            # create a new file called dataset.h5
            fname = os.path.join(self.rootdir, "dataset.h5")
            self.file = h5py.File(fname, "w", libver='latest')
        self.dataset_info_group = self.file.require_group("dataset_info")

        # Create a new group with the current date and time
        now = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.episode_group = self.file.create_group(f"ep_{now}")

        self.step_group = self.episode_group.create_group("steps")
        obs, info = self.env.reset(**kwargs)
        
        self.obs = obs
        self.counter = 0
        return obs, info

    def store(self, obs, reward, terminated, truncated, action, info, task="widowx_put_eggplant_in_basket"):

        step = {
            "observation": self.obs,
            "reward": reward,
            "terminated": terminated,
            "truncated": truncated,
            "action": action,
        }
        # we want to store the observation that conditioned the action
        self.obs = obs

        step_dataset = self.step_group.create_group(f"step_{self.counter}")
        
        for key, value in step.items():
            if key == "observation" and isinstance(value, dict):
                # Create a subgroup for the observation dictionary
                obs_group = step_dataset.create_group(key)
                for obs_key, obs_value in value.items():
                    obs_group.create_dataset(obs_key, data=np.array(obs_value))
            else:
                step_dataset.create_dataset(key, data=np.array(value))


        # Store the info dictionary as a subgroup
        info_group = step_dataset.create_group("info")
        for key, value in info.items():
            if isinstance(value, collections.OrderedDict):
                # Create a subgroup for the OrderedDict
                od_group = info_group.create_group(key)
                for k, s in value.items():
                    od_group.create_dataset(k, data=np.array(s))
            else:
                info_group.create_dataset(key, data=np.array(value))

        self.counter += 1
        
        # add dataset information for that episode
        if terminated or truncated:
            print("called")
            episode_info = {
                "task": task, 
                "n_steps": self.counter, 
                "success": reward > 0.0
            }
            
            episode_info_group = self.dataset_info_group.create_group(self.episode_group.name.split("/")[-1])
            for key, value in episode_info.items():
                episode_info_group.create_dataset(key, data=value)
        

    def step(self, action):
        obs, reward, terminated, truncated, info = self.env.step(action)
        self.store(obs, reward, terminated, truncated, action, info)
        return obs, reward, terminated, truncated, info

    def close(self):
        self.file.close()
        self.env.close()
        

@hydra.main(config_path=improve.CONFIG, config_name="config", version_base="1.3.2")
def main(cfg):

    env = rrl.make(cfg.env)
    env = HDF5LoggerWrapper(env)

    for i in tqdm(range(int(2))):
        obs = env.reset()
        done = False
        while not done:
            action = env.action_space.sample()
            zero = np.zeros_like(action)
            obs, reward, terminated, truncated, info = env.step(zero)

            done = terminated or truncated
    env.close()


if __name__ == "__main__":
    main()
