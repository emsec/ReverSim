from typing import Dict, NamedTuple

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, attribute_keyed_dict, mapped_column, relationship

import app.config as gameConfig
from app.config import (
	ALL_LEVEL_TYPES,
	LEVEL_BASE_FOLDER,
	LEVEL_FILE_PATHS,
	LEVEL_FILETYPES_WITH_TASK,
	REMAP_LEVEL_TYPES,
)
from app.model.SwitchState import SwitchState
from app.model.TimerMixin import TimerMixin
from app.storage.database import LEN_LEVEL_PATH, LEN_LEVEL_TYPE, db
from app.storage.modelFormatError import ModelFormatError
from app.utilsGame import safe_join

# Store some information about a level, so that not every request has to read in 
# the level again
CachedLevel = NamedTuple("CachedLevel", [
	("gateCamouflage", bool), 
	("gateCovert", bool), 
	("randomSwitches", list[int])
])


class Level(db.Model, TimerMixin):
	"""Model to store the player progress of each level. A level is either a task or an info screen/text"""
	levelCache: Dict[str, CachedLevel] = {}

	id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
	phaseID: Mapped[int] = mapped_column(ForeignKey("phase.id"))
	levelPosition: Mapped[int] = mapped_column(default=-1)

	type: Mapped[str] = mapped_column(String(LEN_LEVEL_TYPE))
	fileName: Mapped[str] = mapped_column(String(LEN_LEVEL_PATH))

	switchClicks: Mapped[int] = mapped_column(default=0)
	confirmClicks: Mapped[int] = mapped_column(default=0)
	minSwitchClicks: Mapped[int] = mapped_column(default=-1)
	solved: Mapped[bool] = mapped_column(default=False)
	skipped: Mapped[bool] = mapped_column(default=False)

	# Store the state of randomly assigned switches and all switch states when the level is dirty
	switchStates: Mapped[dict[int, SwitchState]] = relationship(collection_class=attribute_keyed_dict("circuitID"))

	def __init__(self, type: str, fileName: str) -> None:
		if type in REMAP_LEVEL_TYPES:
			type = REMAP_LEVEL_TYPES[type]

		if type not in ALL_LEVEL_TYPES:
			raise ModelFormatError("Unknown level type: " + type + "!")

		self.type = type
		self.fileName = fileName

		# roll values for the switches with random starting state
		for i in self.getRandomSwitchIDs(self.fileName):
			self.switchStates[i] = SwitchState(i, randomInitialState=True)


	def updateSwitches(self, switchStates: dict[str, int]):
		"""Write the list of switch ids and states into the database of the level.
		
		This method will create switches that don't exist yet or update any existing 
		switches.
		"""
		for switch in switchStates.items():
			switchID = int(switch[0])
			switchValue = bool(switch[1])

			# Create the switch if not existent (only random switches will exist on level load)
			if switchID not in self.switchStates:
				self.switchStates[switchID] = SwitchState(switchID, randomInitialState=False)

			# Update the current state of the switch
			self.switchStates[switchID].currentState = switchValue
			

	def isTask(self) -> bool:
		"""True if this level contains a circuit or an alternative task."""
		return self.type in LEVEL_FILETYPES_WITH_TASK


	def isInfoScreen(self) -> bool:
		"""True if this level only contains text / is an info screen, false otherwise.
		
		For e.g. there will be no screenshot folder for info screens.
		"""
		return self.type not in LEVEL_FILETYPES_WITH_TASK


	def getContent(self):
		"""Get the path and how it shall be treated: 
		  - 'text' if the content shall be send straight to the player
		  - 'path' if the content is a path to a file, which can be send with e.g. send_from_directory
		"""
		if self.type in LEVEL_FILE_PATHS:
			return self.fileName, 'path'
		else:
			return self.fileName, 'text'


	def getLogType(self) -> str:
		return ALL_LEVEL_TYPES[self.type]


	def getName(self) -> str:
		"""Name of the level with no file extension. 
		
		Replace the folder separators if you want to use it inside a folder path.
		"""
		return Level.uniformName(self.fileName)


	def isDirty(self) -> bool:
		"""True if the player interacted with the level, false if no confirm/switch was clicked (yet)."""
		return self.switchClicks > 0 or self.confirmClicks > 0


	def hasGate(self, gate: str) -> bool:
		"""Check if the level contains one of the following gates: `camouflage`, `covert`"""
		if self.type != 'level':
			return False
		
		return Level.hasGate2(self.fileName, gate=gate)


	def getCurrentSwitchStates(self) -> dict[int, int]:
		"""Get the current state for all switches"""
		return {k: int(v.currentState) for k, v in self.switchStates.items()}


	def getRandomSwitches(self) -> dict[int, int]:
		"""Get the random values that where rolled for all switches in this level"""
		RAND_SWITCH_IDS = Level.getRandomSwitchIDs(self.fileName)
		return {k: int(v.initialState) for k, v in self.switchStates.items() if k in RAND_SWITCH_IDS}


	def hasRandomSwitches(self) -> bool:
		"""True if there are switches with random starting value in this level"""
		return len(Level.getRandomSwitchIDs(self.fileName)) > 0


	@staticmethod
	def uniformName(fileName: str) -> str:
		"""Used in places like the logfile. 

		The game still uses entire file names internally, to prevent some request and 
		file operations from breaking.
		"""
		return fileName.strip().removesuffix(OPTIONAL_LEVEL_SUFFIX).strip().strip('.')


	@staticmethod
	def hasGate2(fileName: str, gate: str) -> bool:
		"""Check if the level contains one of the following gates: `camouflage`, `covert`"""
		if fileName not in Level.levelCache:
			return False

		if gate == KEY_CAMOUFLAGE:
			return Level.levelCache[fileName].gateCamouflage
		elif gate == KEY_COVERT:
			return Level.levelCache[fileName].gateCovert
		else:
			return False


	@staticmethod
	def getRandomSwitchIDs(fileName: str) -> list[int]:
		"""Get IDs of switches with random starting positions. 
		
		Returns an empty list if there are no random switches in this level 
		(or if the level was not cached)
		"""
		if fileName not in Level.levelCache:
			return []
		
		return Level.levelCache[fileName].randomSwitches
	

	@staticmethod
	def getBasePath(type: str) -> str:
		"""Get the base path of a specific level type, or the level list path if no valid type was specified"""
		if type in LEVEL_FILE_PATHS:
			return safe_join(gameConfig.getAssetPath(), LEVEL_FILE_PATHS[type])
		else:
			return safe_join(gameConfig.getAssetPath(), LEVEL_BASE_FOLDER)


KEY_CAMOUFLAGE = 'camouflage'
KEY_COVERT = 'covert'

OPTIONAL_LEVEL_SUFFIX = '.txt'