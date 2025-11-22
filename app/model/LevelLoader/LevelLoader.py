from abc import ABC, abstractmethod
import logging
import re
from types import MappingProxyType
from typing import Any

from app.model.Level import KEY_CAMOUFLAGE, KEY_COVERT, CachedLevel, Level
from app.model.TutorialStatus import TutorialStatus
from app.utilsGame import LevelType, PhaseType, safe_join


class LevelLoader(ABC):
	CONFIG_KEY_LEVEL_LIST: str|None = None

	def __init__(self,
			phaseName: str, phaseConfig: dict[str, Any],
			tutorialStatus: dict[str, TutorialStatus]
		) -> None:
		self._levels: list[Level]|None = None
		self._phaseName = phaseName
		self._phaseConfig = MappingProxyType(phaseConfig)
		self._tutorialStatus = tutorialStatus


	@abstractmethod
	def loadLevels(self) -> list[Level]:
		"""Generate a list of levels for this phase and player. 
		
		This includes drawing from level pools, shuffling and automatic slide insertions.
		Used by the actual game logic.
		"""
		pass


	@abstractmethod
	def getPossibleLevels(self) -> list[Level]:
		"""Get a the full list of all levels, that could show up during this phase.
		
		Used by the statistics tool and level screenshot tool.
		"""
		pass

	
	def _getLevelLists(self):
		"""Get the file names of the level list and make sure this is an array, even if 
		the array contains only one entry.
		"""
		assert self.CONFIG_KEY_LEVEL_LIST is not None

		levelLists: str|list[str] = self._phaseConfig[self.CONFIG_KEY_LEVEL_LIST]
		if not isinstance(levelLists, list):
			levelLists = [levelLists]

		assert isinstance(levelLists, list), "Expected an array of strings containing the level list names"

		return levelLists


	def _appendLevel(self, slideType: str, fileName: str):
		"""Append a level handling the automatic insertion of tutorials, think aloud etc."""
		assert self._levels is not None, "appendLevel() is used either before initialization or after the LevelBuilder is complete"

		# Get settings from phase config
		thinkaloud = self._phaseConfig.get('thinkaloud', 'no') # "concurrent" | "retrospective" | "no"
		insertTutorials = self._phaseConfig.get('insertTutorials', True)

		# If level info is not found in cache, read the level file
		if slideType == LevelType.LEVEL and fileName not in Level.levelCache:
			try: 
				Level.levelCache[fileName] = self.generateCacheEntry(slideType, fileName)

			except Exception as e:
				logging.error("Exception while generating level cache: " + str(e))

		# Pre Insert Hook
		self._preLevelInsert(
			phaseName=self._phaseName,
			fileType=slideType,
			fileName=fileName,
			tutorialStatus=self._tutorialStatus,
			thinkaloud=thinkaloud,
			insertTutorials=insertTutorials
		)

		# Actually insert the level
		self._appendLevelRaw(slideType=slideType, fileName=fileName)

		# Post Insert Hook
		self._postLevelInsert(
			fileType=slideType,
			phaseName=self._phaseName,
			thinkaloud=thinkaloud
		)


	def _appendLevelRaw(self, slideType: str, fileName: str):
		"""Append the level without calling any of the pre/post level insertion hooks
		
		Also makes sure that the `levelPosition` attribute is updated to ensure proper 
		level order.
		"""
		assert self._levels is not None
		level = Level(type=slideType, fileName=fileName)
		level.levelPosition = len(self._levels)
		self._levels.append(level)
		return level


	def _preLevelInsert(self, phaseName: str, fileName: str, fileType: str, 
			tutorialStatus: dict[str, TutorialStatus], thinkaloud: str,
			insertTutorials: bool
		):

		# Only insert stuff before levels
		if fileType != LevelType.LEVEL:
			return

		# Add concurrent think aloud slide, if configured
		if phaseName == PhaseType.Competition and thinkaloud == 'concurrent':
			self._appendLevelRaw('text', fileName='thinkaloudCon.txt')

		# Insert tutorial slides before levels with camouflage / covert gates, if enabled in the config
		if not insertTutorials:
			return

		if Level.hasGate2(fileName, gate=KEY_COVERT) and KEY_COVERT not in tutorialStatus:
			self._appendLevelRaw(LevelType.TUTORIAL, fileName=KEY_COVERT)
			tutorialStatus[KEY_COVERT] = TutorialStatus(KEY_COVERT) # Mark the covert slide as inserted (not yet shown)

		if Level.hasGate2(fileName, gate=KEY_CAMOUFLAGE) and KEY_CAMOUFLAGE not in tutorialStatus:
			self._appendLevelRaw(LevelType.TUTORIAL, fileName=KEY_CAMOUFLAGE)
			tutorialStatus[KEY_CAMOUFLAGE] = TutorialStatus(KEY_CAMOUFLAGE) # Mark the camou slide as inserted (not yet shown)


	def _postLevelInsert(self, fileType: str, phaseName: str, thinkaloud: str):
		if fileType != LevelType.LEVEL:
			return

		# Add retrospective think aloud slide, if configured
		if phaseName == PhaseType.Competition and thinkaloud == 'retrospective':
			self._appendLevelRaw('text', fileName='thinkaloudRet.txt')


	@staticmethod
	def generateCacheEntry(type: str, name: str):
		"""Read in the entire level file once to gather needed information about the level"""
		covert = False
		camouflage = False

		# Look at the level to determine if a covert / camouflage gate is present
		with open(safe_join(Level.getBasePath(type), name), 'r', encoding='UTF-8') as f:
			txt = f.read()
		covert = re.search("^element§[0-9]*§CovertGate§[0-9]§[0-9]*§[0-9]*§(?!camouflaged)", txt, re.MULTILINE) is not None
		camouflage = re.search("^element§[0-9]*§CovertGate§[0-9]§[0-9]*§[0-9]*§(camouflaged)", txt, re.MULTILINE) is not None
		
		randomSwitches = re.findall("^element§([0-9]*)§Switch§[0-9]§[0-9]*§[0-9]*§random", txt, re.MULTILINE)
		randomSwitches = list(map(int, randomSwitches))

		return CachedLevel(gateCamouflage = camouflage, gateCovert=covert, randomSwitches=randomSwitches)
