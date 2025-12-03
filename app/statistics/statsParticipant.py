from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple, Union, cast

import app.config as gameConfig
from app.statistics.altTasks.AltTaskParser import AltTaskParser

from app.statistics.staticConfig import (
	ENABLE_SPECIAL_CASES,
	EVENT_T,
	GAME_INTRO_PHASES,
	EventNames,
)
from app.statistics.statisticUtils import (
	LogSyntaxError,
	StatisticsError,
	calculateDuration,
	removeprefix,
)
from app.statistics.statsLevel import StatsLevel
from app.statistics.statsPhase import StatsPhase
from app.utilsGame import LogKeys, PhaseType


class StatsParticipant:

	def __init__(self, pseudonym: str, group: Optional[str] = None) -> None:
		self.pseudonym = pseudonym
		self.groups: list[str] = []

		if group is not None:
			self.setGroup(group)

		self.statsPhase: list[StatsPhase] = []
		self.reconnects: list[str] = []
		self.phasesStarted: list[str] = []

		self.reloaded = False
		self.currentPhase = -1
		self.isDebug = False

		self.startTime = None
		self.endTime = None
		self.numEvents: Optional[int] = None

		# Client server time drifts that are bigger than statistics2@timesync_threshold
		self.criticalTimeDrifts: list[float] = []

		# stuff for special case 12:
		if ENABLE_SPECIAL_CASES:
			self.legacyIntros = False
			self.tempLevelStorage: Optional[StatsLevel] = None

		self.onCreateParticipant()


	def handleEvent(self, event: EVENT_T) -> None:
		assert isinstance(event[LogKeys.TIME], datetime)
		assert isinstance(event[LogKeys.EVENT], str)
		
		# Handle all events, that can't be described by a simple dict comparison
		# Special case: The fail quali events can't be handled by the current event system, since the log lines have a bad design
		if event[LogKeys.EVENT].startswith("Failing") and event[LogKeys.EVENT].endswith("Quali Level"):
			return self.onFailQuali(event)
		
		# Special Case: new Level/Info etc
		elif event[LogKeys.EVENT].startswith("new") and LogKeys.FILENAME in event:
			return self.getCurrentPhase().onLevelRequested(event)

		# Handle the standard events
		EVENTS: List[Tuple[EVENT_T, Callable[[EVENT_T], None]]] = [
			# General Events
			(EventNames.GAME_LOADED.value, self.onGameLoaded), # type: ignore
			(EventNames.GROUP_ASSIGNMENT.value, lambda e: self.onGroupAssignment(e)),
			(EventNames.REDIRECT.value, self.onNOP),
			(EventNames.CHANGE_SCENE.value, lambda e: self.onSceneChanged(e)),
			(EventNames.TIME_SYNC.value, self.onTimeSync),

			# Phase specific events
			# NOTE Level request is handled above
			(EventNames.CLICK_NEXT.value, self.onNOP), # old events are called hook! # type: ignore
			(EventNames.SKILL_ASSESSMENT.value, lambda e: self.getCurrentPhase().onSkillAssessment(e)),
			(EventNames.CLICK_INTRO_ARROW.value, lambda e: self.getCurrentPhase().onIntroArrow(e)), # type: ignore
			(EventNames.CLICK_SKIP.value, lambda e:self.getCurrentPhase().getCurrentLevel().onSkip(e)), # type: ignore

			# Level specific events
			(EventNames.STARTED.value, self.onLevelStarted),
			(EventNames.CLICK_SWITCH.value, lambda e: self.getCurrentPhase().onSwitchClick(e)), # type: ignore
			(EventNames.CLICK_CONFIRM.value, lambda e: self.getCurrentLevel().onConfirmClick(e)), # type: ignore
			(EventNames.POPUP_CLICK_FEEDBACK.value, lambda e: self.getCurrentLevel().onLevelSolvedDialogue(e)), # type: ignore

			# Drawing tools
			(EventNames.DRAWTOOLS_PEN.value, lambda e: self.getCurrentPhase().onInteractionDrawing(e)),
			(EventNames.DRAWTOOLS_ERASER.value, lambda e: self.getCurrentPhase().onInteractionDrawing(e)), # type: ignore
			(EventNames.DRAWTOOLS_DELETE.value, lambda e: self.getCurrentPhase().onInteractionDrawing(e)), # type: ignore
			
			# AltTask
			(EventNames.ALT_TASK.value, lambda e: self.getAltTask().handleAltEvent(e))
		]

		# Go through the list and call the corresponding function if one of the events is found
		e = event.items()
		for oe, callback in EVENTS:
			if oe.items() <= e:
				return callback(event)


	# ----------------------------------------
	#              Event Handler
	# ----------------------------------------
	def onNOP(self, event: EVENT_T) -> None:
		pass


	def onCreateParticipant(self):
		pass


	def onLevelStarted(self, event: EVENT_T):
		"""Event: Fired after `EventNames.STARTED`"""
		assert isinstance(event[LogKeys.TIME], datetime)
		assert isinstance(event[LogKeys.TYPE], str)

		# start the already loaded level
		self.getCurrentLevel().onStart(event)


	def onGroupAssignment(self, event: EVENT_T):
		"""Event: Fired after the group assignment. This might be called a second time after SkillAssessment
		
		This method will load all scenes/phases (which will in turn load the necessary levels)
		"""
		self.setGroup(event['Group'])
		
		# Load all phases from the config
		for phaseName in self.getPhases():
			if phaseName == PhaseType.AltTask:
				# TODO Insert your own AltTask implementation here
				phase = AltTaskParser.factory('reversim-conf.statsParser.zvt.ZVT_Task')(phaseName, self.conf)

			# Create a regular phase and register all events
			else:
				phase = StatsPhase(phaseName, self.conf)

			self.statsPhase.append(phase)


	def onGameLoaded(self, event: EVENT_T):
		"""Event: Called after the player loads the page (including first load and refreshes)"""
		# Set the start time if not already set
		if self.startTime is None:
			self.startTime = event[LogKeys.TIME]

		# If no phase is loaded and active return None
		if not self.isPhaseActive():
			playerPosition = "Start"

		else:
			playerPosition = self.getCurrentPhase().name + "(" + str(self.currentPhase) + ")"
			self.reloaded = True
			
			self.getCurrentPhase().onPageReload(event)

			# Run level specific stuff if a level is active
			if self.getCurrentPhase().hasLevels() and self.getCurrentPhase().currentLevel is not None:
				playerPosition += "@" + self.getCurrentLevel().name

		self.reconnects.append(playerPosition)


	def onSceneChanged(self, event: EVENT_T):
		assert isinstance(event['Scene'], str)
		assert event['Scene'] != 'PreloadScene' # Preload scene should be caught by global event

		newPhaseName = event['Scene']

		# If the page was reloaded, drop this SceneChanged event since it is created by the client 
		# jumping to the current scene
		if ENABLE_SPECIAL_CASES and self.reloaded:
			oldPhaseName = self.getCurrentPhase().name
			if newPhaseName != oldPhaseName:
				raise LogSyntaxError("Expected phase " + oldPhaseName + " after page reload, but actually got " + newPhaseName + "!")
			self.reloaded = False
			return

		# Call post on the last phase that was active (or skip this step if this is the first phase)
		if self.currentPhase >= 0:
			self.getCurrentPhase().post(event)

		# Get the next phase from the expected phase list
		self.currentPhase += 1
		expectedPhase = self.getCurrentPhase()

		# Validate and start the next phase
		if expectedPhase.name == newPhaseName:
			self.getCurrentPhase().onStart(event)

		else:
			raise LogSyntaxError("Expected phase " + expectedPhase.name + ", got " + newPhaseName + "!")

		self.phasesStarted.append(expectedPhase.getName())


	def onFailQuali(self, event: EVENT_T):
		self.getCurrentPhase().onFailQuali(event)

		# Insert phases after the current one (should be Quali, is checked by `self.getCurrentPhase().onFailQuali(event)`)
		self.statsPhase.insert(self.currentPhase + 1, StatsPhase(PhaseType.ElementIntro, self.conf, dynamic=True))
		self.statsPhase.insert(self.currentPhase + 2, StatsPhase(PhaseType.Quali, self.conf, dynamic=True))


	def onTimeSync(self, event: EVENT_T):
		assert isinstance(event[LogKeys.TIME], datetime)
		assert isinstance(event[LogKeys.TIME_SERVER], datetime)


	def post(self, event: EVENT_T):
		self.endTime = event[LogKeys.TIME]

		if self.startTime is None:
			raise LogSyntaxError("The participant start time was never set. (Probably onGameLoaded was never called)")

		if self.endTime < self.startTime:
			raise LogSyntaxError("Participant start time " + str(self.startTime) + " should be before end time " + str(self.endTime) + "!")

		# Call post for the current phase (if it is not the GameIntro, see Special Case 11)
		if self.phasesStarted[len(self.phasesStarted)-1] not in GAME_INTRO_PHASES:
			self.getCurrentPhase().post(event)

		# Call post for all following phases that have not been started
		for i in range(self.currentPhase + 1, len(self.statsPhase)):
			self.statsPhase[i].post(event)


	# ----------------------------------------
	#                 Setter
	# ----------------------------------------
	def setGroup(self, group: str) -> None:
		"""Set the currently active group
		
		This method will add the specified group to the list of groups this user belonged to, aswell as loading the phases 
		for the active group
		"""
		group = group.casefold()

		# Check if the group is a debug group (starts with debug). Remove the debug prefix and store the information in `self.isDebug`
		if group.startswith('debug') and group != 'debug':
			self.isDebug = True
			group = removeprefix(group, 'debug')
			# raise LogFiltered("The group " + group + " is a debug group.")

		if group not in gameConfig.groups():
			raise LogSyntaxError("The group " + group + " does not exist!")

		self.groups.append(group)
		self.conf = gameConfig.getGroup(group)


	# ----------------------------------------
	#                 Getter
	# ----------------------------------------
	def getCurrentGroup(self) -> Union[str, None]:
		"""Get the currently active group (note: since the SkillAssessment the player can switch their group during the game)"""
		if len(self.groups): 
			return None
		return self.groups[len(self.groups)-1]


	def getCurrentPhase(self) -> StatsPhase:
		if len(self.statsPhase) < 1:
			raise ValueError("No phases loaded")

		if self.currentPhase < 0:
			raise LogSyntaxError("Some phases are loaded, but none of them is active")

		if self.currentPhase < len(self.statsPhase):
			return self.statsPhase[self.currentPhase]

		raise LogSyntaxError("Invalid phase requested")


	def getCurrentLevel(self) -> StatsLevel:
		return self.getCurrentPhase().getCurrentLevel()


	def getPhases(self) -> List[str]:
		"""Get all phases of the currently active group"""
		try:
			return self.conf['phases'] 
		except Exception:
			raise LogSyntaxError("Error while accessing config (phases)!")


	def isPhaseActive(self) -> bool:
		return len(self.statsPhase) >= 1 and self.currentPhase >= 0


	def getAltTask(self) -> AltTaskParser:
		"""Get the current Phase and make sure that it is of type Alternative"""
		if isinstance(self.getCurrentPhase(), AltTaskParser):
			return cast(AltTaskParser, self.getCurrentPhase())
		else:
			raise LogSyntaxError("The current phase type is not Alternative!")


	# ----------------------------------------
	#               Statistics
	# ----------------------------------------
	def getDuration(self) -> Optional[float]:
		assert isinstance(self.startTime, datetime) and isinstance(self.endTime, datetime)
		return calculateDuration(self.startTime, self.endTime)
	

	def phaseExists(self, name: str) -> bool:
		for phase in self.statsPhase:
			if phase.name.casefold() == name.casefold():
				return True

		return False
	

	def getLevelPhaseMapping(self) -> Dict[str, StatsPhase]:
		"""Get a Dict of all levels and their corresponding phase names
		"""
		returnVal: Dict[str, StatsPhase] = {}

		for phase in self.statsPhase:
			for level in phase.levels:
				returnVal[level.name] = phase

		return returnVal


	def getPhaseByName(self, name: str, firstEntry: bool = False) -> StatsPhase:
		"""Get the StatsPhase object with the specified name. 
		
		Will return the last occurrence of this phase (e.g. the last Quali run), unless `firstEntry` is set to `True`.
		Statistics
		"""
		assert len(name) > 0
		returnVal = None
		for phase in self.statsPhase:
			if phase.name.casefold() == name.casefold():
				returnVal = phase
				if firstEntry:
					break

		if returnVal is None:
			raise StatisticsError("Could not find a phase with name " + name + " in the stats. len(" + str(len(self.statsPhase)) + ").")
		else:
			return returnVal


	def getQualiIterations(self) -> int:
		"""The number of times the quali phase was played. Will be Zero if the phase was never started"""
		self.getPhaseByName(PhaseType.Quali)
		return self.phasesStarted.count(PhaseType.Quali)