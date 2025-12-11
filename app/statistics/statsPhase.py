from datetime import datetime

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from app.config import PHASES_WITH_LEVELS
from app.model.Level import ALL_LEVEL_TYPES
from app.model.LevelLoader.JsonLevelList import JsonLevelList

from app.statistics.staticConfig import ENABLE_SPECIAL_CASES, EVENT_T, LevelStatus, PhaseStatus
from app.statistics.statisticUtils import LogSyntaxError, calculateDuration, removeprefix
from app.statistics.statsLevel import StatsLevel

from app.utilsGame import LevelType, PhaseType


class StatsPhase:
	def __init__(self, name: str, conf: Dict[str, Any], dynamic: bool = False) -> None:
		self.stats = StatsPhase.createStatsPhase()
		self.name = name
		self.levels: List[StatsLevel] = []
		self.currentLevel: Optional[StatsLevel] = None # The level that is currently active
		self.reloadLevel: Optional[StatsLevel] = None
		self.levelCounter = -1
		self.levelPos = -1
		self.status: PhaseStatus = PhaseStatus.NOTSTARTED

		# Dynamically inserted, means the phase is not in the expected outline but instead got loaded by an event
		# 1/True if dynamically inserted, 0/False otherwise
		self.stats['dynamic'] = 1 if dynamic else 0

		self.altTask = None

		self.startTime = None
		self.endTime = None

		# Load all levels
		if self.hasLevels():
			self.levelCounter = 0
			self.levelPos = 0
			for type, name in self.generateLevels(conf):
				level = StatsLevel(type, name)
				self.levels.append(level)


	def post(self, event: EVENT_T):
		assert isinstance(event['Time'], datetime)

		# If the phase was never started, set it to never reached
		if self.status == PhaseStatus.NOTSTARTED:
			self.status = PhaseStatus.NOTREACHED
		# If phase is in progress, check if one of the levels is not solved.
		elif self.status == PhaseStatus.INPROGRESS:
			self.status = PhaseStatus.SOLVED
			for level in self.levels:
				if level.stats['status'] not in [LevelStatus.SOLVED, LevelStatus.SKIPPED]:
					self.status = PhaseStatus.ABORTED
					break
		
		# Call post for all levels
		if self.hasLevels():
			if self.currentLevel is None and self.status != PhaseStatus.NOTREACHED:
				raise LogSyntaxError("Ending phase with levels, but no level was ever loaded " + self.name + ".")

			# Call post for the currently active level (will set the end time)
			if self.currentLevel is not None:
				self.getCurrentLevel().post(event)

			# Call post to make sure all levels in this phase are terminated. 
			# NOTE: Calling post ON A LEVEL multiple times is not harmful
			for level in self.levels:
				level.post(None)

		# Set the end time, if the phase was started
		if self.status != PhaseStatus.NOTREACHED:
			self.endTime = event['Time']

			try:
				assert isinstance(self.startTime, datetime)
				calculateDuration(self.startTime, self.endTime)
			except Exception:
				# Ignore errors on the final scene, since the timing of redirect and gameover events are imprecise
				if self.name != PhaseType.FinalScene:
					raise LogSyntaxError("Phase start time " + str(self.startTime) + " should be before " + str(self.endTime) + "!")


	def hasLevels(self) -> bool:
		return self.name in PHASES_WITH_LEVELS


	def generateLevels(self, conf: Dict[str, Any]) -> List[Tuple[str, str]]:
		"""Build the levels/info screens index for the currently active phase 
		(in the order specified in the levels list)
		"""
		if not self.hasLevels():
			raise LogSyntaxError("Tried to get all levels from " + self.name + ", but the phase has none!")
		
		assert isinstance(JsonLevelList.singleton, dict), "The JsonLevelList cache was not populated"

		try:
			# The level loader needs to be recreated for every phase as it has internal state
			levels = JsonLevelList(
				phaseName=self.name, phaseConfig=conf[self.name], tutorialStatus={},
				levelList=JsonLevelList.singleton
			).getPossibleLevels()

			# We just need a simple list with tuple(levelType, levelName)
			return [(level.type, level.getName()) for level in levels]

		except Exception as e:
			logging.error(e)
			raise LogSyntaxError("Error while accessing config (levels)!")


	def getCurrentLevel(self) -> StatsLevel:
		if not self.hasLevels():
			raise LogSyntaxError("The phase " + self.name + " has no levels by design!")

		if len(self.levels) < 1:
			raise LogSyntaxError("No levels where loaded for " + self.name + "!")

		if self.currentLevel is None:
			raise LogSyntaxError("No level is active in phase " + self.name + "!")

		assert not self.levelCounter < 0 # NOTE: Dont move assertion up
		return self.currentLevel


	def onStart(self, event: EVENT_T):
		assert isinstance(event['Time'], datetime)
		# Should have already been validated inside onSceneChanged, if not assertion fails
		assert self.name == event['Scene'], "Started the wrong scene, expected " + self.name + ", got " + event['Scene']

		self.status = PhaseStatus.INPROGRESS
		self.startTime = event['Time']


	def onFailQuali(self, event: EVENT_T):
		# Check preconditions
		if self.name != PhaseType.Quali:
			raise LogSyntaxError("Failed quali found in log, but current scene is: " + self.name + "!")

		activeLevel = self.getCurrentLevel()
		activeLevel.onFail(event)

		self.status = PhaseStatus.FAILED
		self.post(event)


	def onSwitchClick(self, event: EVENT_T):
		self.stats['switchClicks'] += 1
		if self.name == PhaseType.DrawTools or self.name == PhaseType.ElementIntro:
			if 'Switch ID' in event: # NOTE 'solvingState' not in event does not work right now
				raise LogSyntaxError('Missing attrib solvingState for non level switch click in phase ' \
						 + self.name + '.')
		else:
			# TODO FIXME The switch clicks are messed up in `clow_11111101_random`
			#if 'Solving State' in event:
			#	raise LogSyntaxError('Got non level switch click in level ' + self.getCurrentLevel().name + '.')
			self.getCurrentLevel().onSwitchClick(event)


	def onInteractionDrawing(self, event: EVENT_T):
		"""The user used one of the drawing tools and a screenshot should have been created 
		
		(pen, eraser, delete button)
		"""
		self.stats['drawn'] += 1

		if self.name == PhaseType.DrawTools:
			pass
		else:
			self.getCurrentLevel().onInteractionDrawing(event)


	def onLevelRequested(self, event: EVENT_T):
		"""Called directly by statsParticipant when `new LevelName` occurs in the log"""
		assert self.levelCounter >= 0
		assert 'Filename' in event and isinstance(event['Filename'], str)

		# Prevent array index out of bounds
		if self.levelCounter > len(self.levels)-1:
			raise LogSyntaxError("Reached end of phase, but another level was requested: " + event['Filename'] + ".")

		# Reset the skip loaded thinkaloud flag
		self.skipNextInfoBegin = False

		# If the page was reloaded, do not load the next level but instead restart the current one
		if ENABLE_SPECIAL_CASES and self.reloadLevel is not None:
			self.reloadLevel.onLoad(event, self.reloadLevel.position)
			self.reloadLevel = None
			return

		nextLevel = None
		nextLevelType: str = removeprefix(event['Event'], "new ").strip()
		nextLevelName: str = event['Filename']
		expectedLevelType: str = ALL_LEVEL_TYPES[self.levels[self.levelCounter].type]

		# Check if the current level type matches the expected level type
		if nextLevelType != expectedLevelType:
			# Tutorials might get inserted dynamically
			if nextLevelType in [ALL_LEVEL_TYPES[LevelType.TUTORIAL], ALL_LEVEL_TYPES[LevelType.SPECIAL]]:
				nextLevelTypeLog = next(k for k, v in ALL_LEVEL_TYPES.items() if v == nextLevelType)
				tut = StatsLevel(nextLevelTypeLog, nextLevelName)
				self.levels.insert(self.levelCounter, tut)
				nextLevel = tut

			# We might have too many levels in the que, since the new JSON Level List 
			# allows to pick one of multiple levels. Try to skip ahead to find a slide 
			# with matching type
			elif nextLevelType in ALL_LEVEL_TYPES[LevelType.INFO]:
				oldLevelCounter = self.levelCounter
				for level in self.levels[self.levelCounter:]:				
					# Break if we found a slide with matching type
					if ALL_LEVEL_TYPES[level.type] == nextLevelType:
						nextLevel = self.levels[self.levelCounter]
						assert nextLevel == level
						break
						
					# Increment counter and check if we reached the end of the phase
					self.levelCounter += 1
					if self.levelCounter > len(self.levels)-1:
						raise LogSyntaxError(f'Unable to find a slide of type {nextLevelType} until the end of the phase')

			# Unable to find a matching slide with all edge cases, raise error
			else:
				raise LogSyntaxError("Expected slide of type " + expectedLevelType + ", got " + nextLevelType + " in " + self.name + "!")

		# If the level contains a circuit, the order might be randomized, so search for the level in the array
		if nextLevelType in [ALL_LEVEL_TYPES['level'], ALL_LEVEL_TYPES['tutorial']]:
			for level in self.levels:
				if nextLevelName == level.name:
					nextLevel = level
					break

		# Otherwise the level should be in the expected position
		else:		
			# Validate that the level name matches
			if nextLevelName == self.levels[self.levelCounter].name:
				nextLevel = self.levels[self.levelCounter]
			else:
				raise LogSyntaxError("Level " + nextLevelName + " was not expected.")

		# Check if a level/circuit with that name was found
		if nextLevel is None:
			raise LogSyntaxError("Could not find a level with the name " + nextLevelName + " in the expected level list.")			

		self.nextLevel(event, nextLevel)
		

	def nextLevel(self, event: EVENT_T, nextLevel: StatsLevel):
		# Call post for the last level
		if self.currentLevel is not None:
			self.getCurrentLevel().post(event)

		# Set the new level as active, register all events that belong to the level and call onStart
		self.currentLevel = nextLevel
		nextLevel.onLoad(event, self.levelPos)
		self.levelCounter += 1

		# If the level is a task, increment the counter for the individual level pos (cause the tasks might be shuffled)
		if nextLevel.isTask():
			self.levelPos += 1
		return


	def onSkillAssessment(self, event: EVENT_T):
		assert 'Score' in event
		score = int(event['Score'])

		if self.name != PhaseType.Skill:
			raise LogSyntaxError('Expected phase SkillAssessment, got ' + self.name + "!")

		# TODO Write check for the skill calculation
		self.stats['skill'] = score

	
	def onPageReload(self, event: EVENT_T):
		# Run level specific stuff if a level is active
		if self.hasLevels() and self.currentLevel is not None:
			currentLevel = self.getCurrentLevel()
			currentLevel.onPageReload()

			# Flag this level to be handled inside self.onLevelRequested() later
			if ENABLE_SPECIAL_CASES:
				self.reloadLevel = currentLevel


	def onIntroArrow(self, event: EVENT_T):
		"""Called when the user navigates inside IntroduceElements"""
		if self.name != PhaseType.ElementIntro:
			raise LogSyntaxError("Intro navigation outside of IntroduceElements.")


	# ----------------------------------------
	#          Getter / Statistics
	# ----------------------------------------
	def getName(self) -> str:
		REMAP_NAMES = {
			'GameIntroND': PhaseType.Start,
			'FinalSceneNPS': PhaseType.FinalScene
		}
		if self.name in REMAP_NAMES:
			return REMAP_NAMES[self.name]
		else:
			return self.name


	def getDuration(self) -> float:
		"""Get the duration the player spend in this phase, or -1 if the phase was never started."""
		if self.status == PhaseStatus.NOTREACHED:
			return -1

		assert isinstance(self.startTime, datetime)
		assert isinstance(self.endTime, datetime)
		return calculateDuration(self.startTime, self.endTime)

	
	def getTasks(self) -> List[StatsLevel]:
		levels: List[StatsLevel] = []
		for level in self.levels:
			if level.isTask(): 
				levels.append(level)
		
		return levels


	def getAttribute(self, attribute: str) -> Union[str, int, float, bool, PhaseStatus]:
		# Phase attribute requested
		P_ATTRIBS: Dict[str, Any] = {
			'status': self.status,
			'started': self.getStarted(),
			'duration': self.getDuration(),
			**self.stats
		}

		return P_ATTRIBS[attribute]


	def getStarted(self) -> bool:
		return self.status not in [PhaseStatus.NOTREACHED, PhaseStatus.NOTSTARTED]


	def getLevelByName(self, name: str) -> StatsLevel:
		for level in self.levels:
			if level.name == name:
				return level
			
		raise KeyError("Could not find a level with name " + name)


	# ----------------------------------------
	#             Static Methods
	# ----------------------------------------
	@staticmethod
	def getOrdinalNumber(cardinalNumber: int) -> str:
		NUMBER_WORDS = ["0th", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth"]
		if cardinalNumber < len(NUMBER_WORDS):
			return NUMBER_WORDS[cardinalNumber]
		else:
			return str(cardinalNumber) + "th"


	@staticmethod
	def createStatsPhase() -> Dict[str, int]:
		return {
			'switchClicks': 0,
			'confirmClicks': 0,
			'levelsSolved': 0,
			'levelsSkipped': 0,
			'drawn': 0,
			'skill': -1,
			'dynamic': 0
		}

# 'concurrent', 'retrospective', 'no' or undefined
THINKALOUD_CONFIG_OPTIONS = ['concurrent', 'retrospective']
THINKALOUD_SLIDE_NAMES = ['thinkaloudCon', 'thinkaloudRet'] 

INTRO_SLIDE_NAMES = ['covert', 'camouflage']
INTRO_SLIDE_NAMES_OLD = {
	'Tutorial covert': INTRO_SLIDE_NAMES[0], 
	'Tutorial camouflage': INTRO_SLIDE_NAMES[1]
} # Special case 12