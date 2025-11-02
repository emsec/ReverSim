from copy import deepcopy
import logging
import random
from types import MappingProxyType
from typing import Any, NamedTuple

from app.model.Level import Level
from app.model.LevelLoader.LevelLoader import LevelLoader
from app.model.TutorialStatus import TutorialStatus
from app.utilsGame import LevelType
from app.config import load_config

CONFIG_KEY_LEVEL_LIST = 'pools'

class LeanSlide(NamedTuple):
	slideType: LevelType
	fileName: str


class JsonLevelList(LevelLoader):
	singleton: dict[str, Any]|None = None


	def __init__(self,
		phaseName: str,
		phaseConfig: dict[str, Any],
		tutorialStatus: dict[str, TutorialStatus],
		levelList: dict[str, Any]
	) -> None:
		super().__init__(phaseName, phaseConfig, tutorialStatus)

		self.levelList = levelList
		self.pool: dict[str, list[dict[str, Any]|list[dict[str, Any]]]] = {}


	def loadLevels(self) -> list[Level]:
		"""
		
		NOTE: This method is single use. After you have loaded the levels for a 
		Player/Phase combo, you have to create a new `JsonLevelList`.
		"""
		self._levels = []
		list_names: str|list[str] = self._phaseConfig[CONFIG_KEY_LEVEL_LIST]
		if isinstance(list_names, str):
			list_names = [list_names]
		assert isinstance(list_names, list), "Expected an array of strings containing the level list names"

		for list_name in list_names:
			self.parse_list(list_name)

		assert self._levels is not None and len(self._levels) > 0, "No levels have been loaded, this is probably an error"
		return self._levels


	def parse_list(self, list_name: str):
		# read only, since this is loaded from a JSON and we wan't no side effects.
		# But be careful, this is not a frozendict, children can still be modified
		current_list = MappingProxyType(self.levelList[list_name])

		# Load settings from current_list
		amount: int|str|list[str] = current_list.get('amount', 'all')
		shuffle: bool = current_list.get('shuffle', False)
		eliminate: bool = current_list.get('eliminate', True)
		shuffle_amount: bool = current_list.get('shuffle_amount', True)

		# We are working on a copy of the current_list to allow for elimination of levels.
		# We call this copy pool and we only store the actual level list
		if list_name not in self.pool:
			self.pool[list_name] = deepcopy(current_list['levels'])
		
		# Shuffle the pool if enabled
		if shuffle:
			random.shuffle(self.pool[list_name])

		# Set amount to length of pool if we wan't to load all levels (default)
		if amount == 'all':
			amount = len(self.pool[list_name])

		if isinstance(amount, int):
			self.load_entries(self.pool[list_name], list_name, amount, eliminate)

		# Special case for when we need multiple versions/difficulties of the same task
		# and the task group shall only be shown once
		elif isinstance(amount, list):
			assert eliminate, "This configuration only makes sense with eliminate enabled"
			self.load_entries_multiversion(self.pool[list_name], list_name, amount, shuffle_amount)

		else:
			raise ValueError('An invalid value for amount has made it through the pre checks')


	def load_entries(self,
			current_pool: list[dict[str, Any] | list[dict[str, Any]]],
			list_name: str,
			amount: int,
			eliminate: bool
		):
		# Check that the validator has caught all invalid edge cases
		assert amount > 0, f'Amount of pool "{list_name}" must be > 0, got {amount}'
		assert amount <= len(current_pool), f'Requested {amount} levels from pool "{list_name}" but the pool only contains {len(current_pool)} levels'

		for i in range(0, amount):
			entry = current_pool[0 if eliminate else i]
			assert not isinstance(entry, list), "Level Groups are not allowed when the amount is an integer or 'all'!"
			self._appendLevel(slideType=entry['type'], fileName=entry['name'])
			
			# Remove entry from pool if it shall only be shown once
			if eliminate:
				current_pool.remove(entry)


	def load_entries_multiversion(self,
		current_pool: list[dict[str, Any] | list[dict[str, Any]]],
		list_name: str,
		amount: list[str],
		shuffle_amount: bool
	):
		group_order = amount.copy()
		assert all(len(level_group) == len(group_order) for level_group in current_pool), f"Something in {list_name} slipped through the validator"

		# Shuffle the level group order if enabled
		if shuffle_amount:
			random.shuffle(group_order)

		# Draw exactly one level of each group in the specified order (might be randomized)
		for group_name in group_order:
			level_group = current_pool.pop(0)
			assert isinstance(level_group, list), "Please specify a list that contains one level of each group"
			entry = [level for level in level_group if level['group'] == group_name]
			assert len(entry) == 1, "There should be exactly one entry matching this group in the level_group"
			self._appendLevel(slideType=entry[0]['type'], fileName=entry[0]['name'])


	@staticmethod
	def fromFile(
		fileName: str = 'conf/levelList.json',
		instanceFolder: str = 'instance'
	) -> dict[str, Any]:
		"""Load all level lists from `conf/levelList.json` into a `dict`"""

		try:
			conf = load_config(fileName=fileName, instanceFolder=instanceFolder)

			# TODO Run checks

			logging.info(f'Successfully loaded {len(conf)} level lists.')
			return conf
			
		except Exception as e:
			logging.info(f'No level lists loaded from "{fileName}".')
			logging.debug(e)
			return {}
