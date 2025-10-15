from abc import ABC, abstractmethod
import re
from typing import Any

from app.model.Level import KEY_CAMOUFLAGE, KEY_COVERT, CachedLevel, Level
from app.model.TutorialStatus import TutorialStatus
from app.utilsGame import PhaseType, safe_join


class LevelLoader(ABC):

	def __init__(self,
			phaseName: str, phaseConfig: dict[str, Any],
			tutorialStatus: dict[str, TutorialStatus]
		) -> None:
		self._levels: list[Level]|None = None
		self._phaseName = phaseName
		self._phaseConfig = phaseConfig
		self._tutorialStatus = tutorialStatus


	@abstractmethod
	def loadLevels(self) -> list[Level]:
		pass


	def _appendLevel(self, slideType: str, fileName: str):
		assert self._levels is not None, "appendLevel() is used either before initialization or after the LevelBuilder is complete"

		thinkaloud = self._phaseConfig.get('thinkaloud', 'no') # "concurrent" | "retrospective" | "no"
		insertTutorials = self._phaseConfig.get('insertTutorials', True)

		self._preLevelInsert(
			phaseName=self._phaseName,
			fileType=slideType,
			fileName=fileName,
			tutorialStatus=self._tutorialStatus,
			thinkaloud=thinkaloud,
			insertTutorials=insertTutorials
		)
		self._levels.append(Level(type=slideType, fileName=fileName))
		self._postLevelInsert(
			fileType=slideType,
			phaseName=self._phaseName,
			thinkaloud=thinkaloud
		)


	def _preLevelInsert(self, phaseName: str, fileName: str, fileType: str, 
			tutorialStatus: dict[str, TutorialStatus], thinkaloud: str,
			insertTutorials: bool
		):
		# Only insert stuff before levels
		if fileType != 'level':
			return

		# Add concurrent think aloud slide, if configured
		if phaseName == PhaseType.Competition and thinkaloud == 'concurrent':
			self._appendLevel('text', fileName='thinkaloudCon.txt')

		# Insert tutorial slides before levels with camouflage / covert gates, if enabled in the config
		if not insertTutorials:
			return

		if Level.hasGate2(fileName, gate=KEY_COVERT) and KEY_COVERT not in tutorialStatus:
			self._appendLevel('tutorial', fileName=KEY_COVERT)
			tutorialStatus[KEY_COVERT] = TutorialStatus(KEY_COVERT) # Mark the covert slide as inserted (not yet shown)

		if Level.hasGate2(fileName, gate=KEY_CAMOUFLAGE) and KEY_CAMOUFLAGE not in tutorialStatus:
			self._appendLevel('tutorial', fileName=KEY_CAMOUFLAGE)
			tutorialStatus[KEY_CAMOUFLAGE] = TutorialStatus(KEY_CAMOUFLAGE) # Mark the camou slide as inserted (not yet shown)


	def _postLevelInsert(self, fileType: str, phaseName: str, thinkaloud: str):
		if fileType != 'level':
			return

		# Add retrospective think aloud slide, if configured
		if phaseName == PhaseType.Competition and thinkaloud == 'retrospective':
			self._appendLevel('text', fileName='thinkaloudRet.txt')


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
