from copy import deepcopy
import logging
from random import randrange
from typing import Any, NamedTuple

from app.model.Level import Level
from app.model.LevelLoader.LevelLoader import LevelLoader
from app.model.TutorialStatus import TutorialStatus
from app.utilsGame import LevelType
from app.config import load_config


class LeanSlide(NamedTuple):
	slideType: LevelType
	fileName: str


class JsonLevelList(LevelLoader):

	def __init__(self,
		phaseName: str,
		phaseConfig: dict[str, Any],
		tutorialStatus: dict[str, TutorialStatus],
		levelList: dict[str, Any]
	) -> None:
		super().__init__(phaseName, phaseConfig, tutorialStatus)
		self.levelList = levelList

		self.action_types = {
			'take_random': '',
			'take_from_multiversion': ''
		}

		self.pool: dict[str, list[dict[str, Any]]] = {}


	def loadLevels(self) -> list[Level]:
		self._levels = self.parse_entry({}) # TODO

		assert self._levels is not None and len(self._levels) > 0, "No levels have been loaded, this is probably an error"
		return self._levels


	def consume_from_list(self, list_name: str, amount: int, random: bool):
		assert self._levels is not None
		assert list_name in self.levelList, f'"{list_name}" is not in the level list json, this should have been caught by the validator!'

		levels: list[LeanSlide] = []

		if list_name not in self.pool:
			self.pool[list_name] = deepcopy(self.levelList[list_name])

		len_pool = len(self.pool[list_name])
		if len_pool < 1:
			logging.error(f'Trying to draw a level from pool "{list_name}" which is depleted!')
		if amount > len_pool:
			logging.error(f'Trying to draw {amount} levels from pool "{list_name}" which only got {len_pool} levels')
			amount = len_pool

		level_list = self.levelList[list_name]
		if amount < 1:
			amount = len(level_list)

		for _ in range(amount):
			pop_index = randrange(len_pool) if random else 0
			entry = self.pool[list_name].pop(pop_index)
			levels.extend(self.parse_entry(entry))

		return levels


	def parse_entry(self, entry: dict[str, Any]) -> list[LeanSlide]:
		entry_type = entry['type']
		
		if entry_type in LevelType:
			return [LeanSlide(slideType=entry['type'], fileName=entry['name'])]
		elif entry_type == 'take':
			return self.consume_from_list(
				list_name=entry['from'],
				amount=entry.get('amount', 0),
				random=entry.get('random', False)
			) # TODO
		else:
			return []


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


