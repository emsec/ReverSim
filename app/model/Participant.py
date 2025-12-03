import logging
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import String
from sqlalchemy.orm import (
	Mapped,
	attribute_keyed_dict,
	mapped_column,
	reconstructor, # type: ignore
	relationship,
)

import app.config as gameConfig
from app.model.GroupStats import GroupStats
from app.model.Level import ALL_LEVEL_TYPES, Level
from app.model.LogEvents import (
	AltTaskEvent,
	ChronoEvent,
	ClickEvent,
	ConfirmClickEvent,
	DrawEvent,
	GroupAssignmentEvent,
	IntroNavigationEvent,
	LanguageSelectionEvent,
	LevelState,
	PopUpEvent,
	QualiEvent,
	SelectDrawToolEvent,
	SimulateEvent,
	SkillAssessmentEvent,
	StartSessionEvent,
	SwitchClickEvent,
)
from app.model.Phase import Phase, TutorialStatus
from app.router.jsonRPC import JsonRPC_Errcode, JsonRPC_Error
from app.storage.database import LEN_GROUP, LEN_SESSION_ID, SanityVersion, db
from app.storage.modelFormatError import ModelFormatError
from app.storage.ParticipantLogger import ParticipantLogger
from app.utilsGame import (
	X_TRUE,
	EventType,
	IntroLabels,
	LevelType,
	PhaseType,
	ServerTime,
	getCircuitStatusLog,
	now,
)


class Participant(db.Model, SanityVersion):
	"""Model to represent a participant in the study 

	Planning to follow the Model View Controller approach
	"""

	pseudonym: Mapped[str] = mapped_column(String(gameConfig.PSEUDONYM_LENGTH), primary_key=True)
	group: Mapped[str] = mapped_column(String(LEN_GROUP))
	isDebug: Mapped[bool] = mapped_column(default=False)
	phaseIdx: Mapped[int] = mapped_column(default=0)

	# Network state
	packetIndex: Mapped[int] = mapped_column(default=0)
	sessionID: Mapped[str] = mapped_column(String(LEN_SESSION_ID), default='')
	lastConnection: Mapped[ServerTime] = mapped_column()

	# Drift between client and server time
	timeDelta: Mapped[Optional[int]] = mapped_column(default=None)

	# Game state
	failedQuali: Mapped[bool] = mapped_column(default=False)
	startedPresurvey: Mapped[bool] = mapped_column(default=False)
	startedGame: Mapped[bool] = mapped_column(default=False)
	startedFinal: Mapped[bool] = mapped_column(default=False)
	startedPostsurvey: Mapped[bool] = mapped_column(default=False)
	pauseShown: Mapped[bool] = mapped_column(default=False)

	# Keep track of automatically inserted tutorial slides
	introProgress: Mapped[int] = mapped_column(default=-1)
	introPos: Mapped[int] = mapped_column(default=-1)
	tutorialStatus: Mapped[Dict[str, TutorialStatus]] = relationship(collection_class=attribute_keyed_dict("name"))

	# Check if logging is enabled (affects creation of screenshots and logfiles)
	loggingEnabled: Mapped[bool] = mapped_column(default=True)
	
	phases: Mapped[List[Phase]] = relationship(back_populates="participant")


	def __init__(self, pseudonym: str, group: str, isDebug: bool) -> None:
		# Player Info
		# Group will be set later by `self.setGroup()`
		self.pseudonym = pseudonym
		self.lastConnection = now()
		self.isDebug = isDebug

		# Check if logging is enabled (affects creation of screenshots and logfiles)
		self.loggingEnabled = gameConfig.isLoggingEnabled(group)
		self.init_on_load()

		# determine a level group. Use the lastConnection as timestamp for the log event
		self.setGroup(group, self.lastConnection)


	@reconstructor
	def init_on_load(self):
		"""When the object is loaded from the database, the constructor is not run again!"""
		self.logger = ParticipantLogger(self.pseudonym, self.loggingEnabled)


	def nextPhase(self, timeStamp: int) -> str:
		"""Proceed to the next phase"""
		assert len(self.phases) > 0, "The phase is still None, looks like `startGame()` or `self.loadPhase()` was never called!"

		# Do not leave the level editor
		if self.getPhaseName() == PhaseType.Editor:
			return self.getPhaseName()

		# Return to the quali phase after the user has been thrown back to ElementIntroduction
		# The scene to return to is determined by the phaseIdx (should always be quali tho)
		if self.failedQuali:
			self.failedQuali = False
			self.phaseIdx -= 1 # Phase index will be incremented again after next call to `next()`
			return self.loadPhase(timeStamp, PhaseType.ElementIntro)
		else:
			self.phaseIdx += 1

		# If in SkillAssessment, assign the user to a new group
		if self.getPhaseName() == PhaseType.Skill:
			newGroup, score = self.getPhase().skillAssessment()
			self.logger.writeToLog(EventType.SkillAssessment, "§Score: " + str(score), now())

			event = SkillAssessmentEvent(
				clientTime=int(timeStamp), serverTime=now(),
				pseudonym=self.pseudonym,
				phase=self.getPhaseName(),
				score=score
			)
			event.setPlayerContext(self.pseudonym)
			event.commit()

			if newGroup is not None:
				self.setGroup(newGroup, timeStamp)
			else:
				logging.error("Error: No new group could be determined. Is the SkillGroups entry empty?")

		return self.loadPhase(timeStamp)


	def loadPhase(self, timeStamp: int, phaseName: Optional[str] = None) -> str:
		"""Load the scene specified by phaseIdx"""

		# Get the next scene/phase
		if self.phaseIdx >= len(gameConfig.getGroup(self.group)['phases']):
			return 'finished' # No more scenes, reached the end of the game

		# Get the next phase name from the group config if not passed as a parameter
		if phaseName is None:
			phaseName = Participant.convertPhaseIndex(self.group, self.phaseIdx)

		phase = Phase(phaseName, len(self.phases), self.getConfig().get(phaseName, {}), self.logger)
		self.phases.append(phase)
		db.session.add(phase)
		db.session.commit() # Otherwise parameters are not initialized/None

		self.logger.logNewPhase(timeStamp, self.getPhaseName())
		
		event = ChronoEvent(
			clientTime=int(timeStamp),
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=None,
			operation='load',
			timerType='phase',
			context=self.getPhaseName(),
			limit=self.getPhase().getTimeLimit()
		)
		event.commit()

		# Load phase related stuff like levels (they might also generate log entries)
		phase.load(timeStamp, self.tutorialStatus)
		
		return phaseName


	def failQuali(self, timeStamp: Optional[str] = None): 
		"""The player needed too many switch/confirm clicks and shall be thrown back to element introduction.
		
		The phaseIdx will be left untouched, after the ElementIntroduction the player will be send back to the 
		scene where he left.
		"""
		if self.getPhaseName() != PhaseType.Quali:
			logging.error("Failed quali " + self.pseudonym + " but current phase is " + self.getPhaseName() + "!")
			return

		self.failedQuali = True
		self.introPos = 0 # -1 would show the very first slide, but the slide does not make sense for repetition


	def getPhaseName(self) -> str:
		"""Get the name of the currently active phase from the Phase model or return 'finished', 
		if the player reached the end of the game (phaseIdx > num configured phases).
		"""
		if self.phaseIdx > len(gameConfig.getGroup(self.group)['phases']):
			return 'finished'

		return self.getPhase().name


	def getPhase(self) -> Phase:
		"""Get the instance of the currently active phase for this player
		
		Even if the phase name (`getPhaseName()`) is equal for each player, the instances returned by this method 
		are not because the phases store player specific data.
		"""
		assert len(self.phases) > 0, "The phase is still None, looks like `startGame()` or `self.loadPhase()` was never called!"
		return self.phases[-1]


	def isLastPhase(self) -> bool:
		"""Return True, if this is the last phase configured for this group. Will return False otherwise."""
		return self.phaseIdx >= len(gameConfig.getGroup(self.group)['phases'])-1


	def getLevelContext(self) -> tuple[LevelType, str]:
		assert self.getPhase().hasLevels(), "getLevelContext() called on a Phase without levels"
		level = self.getPhase().getLevel() 
		assert level.type in LevelType, "Invalid level type"
		return LevelType(level.type), level.getName()
	

	def getLink(self, linkName: str, params: dict[str, str], lang: str = gameConfig.getDefaultLang()):
		"""Get the redirect link to the preSurvey / postSurvey, or None if not specified
		
		example config entry: https://survey.academiccloud.de/index.php/123456?ui={ui}&lang={lang}&group={group}

		{ui}, {group}, {lang} and {timeStamp} will be replaced with the pseudonym, group and chosen language
		"""
		assert linkName in ['urlPreSurvey', 'urlPostSurvey']
		
		# If no link is configured, return None. 
		link = self.getGamerules().get(linkName, None)
		if not isinstance(link, str):
			return None

		# Generate empty string value for keys missing in `params`
		constant_factory = lambda : ''  # noqa: E731

		# Add all the fixed keys to the params list (the fixed keys will override existing keys)
		minimumParams: dict[str, str|int] = {'ui': self.pseudonym, 'lang': lang, 'group': self.group, 'timeStamp': now()}
		mergedParams = defaultdict(constant_factory, {**minimumParams, **params})

		return link.format_map(mergedParams)


	def getConfig(self):
		"""Return the config for the group this user is in.
		
		This also contains the gamerules, which are misleadingly stored in the attribute 'config')"""
		if self.group is None: # type: ignore
			raise ModelFormatError("Invalid state: The group is still None")
		
		return gameConfig.getGroup(self.group)


	def getGamerules(self) -> Dict[str, Any]:
		"""Get the gamerules for this group"""
		return self.getConfig()['config']


	def setGroup(self, newGroup: str, timeStamp: Union[str, int]):
		"""Assign this user to a specific group
		
		This method will add a logfile entry if logging is enabled.
		"""
		# Update the model
		# Make sure we start at the beginning, especially when switching groups after the Skill Assessment
		self.group, _ = Participant.createGroup(newGroup)

		# Log the group assignment if configured
		if self.loggingEnabled:
			msg = '§Group: ' + newGroup
			self.logger.writeToLog(EventType.GroupAssignment, msg, timeStamp)

		event = GroupAssignmentEvent(
			clientTime=int(timeStamp), serverTime=now(),
			pseudonym=self.pseudonym,
			group=self.group,
			isDebug=self.isDebug
		)
		event.commit()

		# Load the first phase for this group
		self.phaseIdx = 0

		return self.group


	# --------------------- #
	#       RPC Stuff       #
	# --------------------- #

	def startGame(self, timeStamp: int):
		self.logger.writeToLog(EventType.PhaseRequested, '§Scene: PreloadScene', timeStamp)

		globalLimit = self.getGlobalTimerDuration(gameConfig.TIMER_NAME_GLOBAL_LIMIT)
		globalLimit = globalLimit if globalLimit > 0 else None

		event = ChronoEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase='PreloadScene',
			level=None,
			operation='start',
			timerType='phase',
			context='PreloadScene',
			limit=globalLimit
		)
		event.commit()

		if not self.startedGame:
			self.startedGame = True
			self.loadPhase(timeStamp)

			if len(self.phases) < 1: # type: ignore
				raise ModelFormatError("Invalid state: The Phase is still invalid")
			
			GroupStats.increasePlayersStarted(self.group, self.isDebug)


	def status(self, timeStamp: Union[str, int], recursionBreaker: bool = False) -> Dict[str,Any]:
		"""Get the current state of the game for this player
		
		This will always include the current phase, additionally it might include the following:
		 - The currently active level, if this phase got some
		 - The time remaining, if a timer was started for the current phase/level
		"""
		phase = self.getPhase()

		status: Dict[str, Union[str, int, dict[int, int]]] = {
			"phase": self.getPhaseName()
		}

		phaseDuration = phase.getTimeLimit()
		if phaseDuration is not None:
			status['timerPhaseStart'] = phase.getStartTime()
			status['timerPhaseDuration'] = phaseDuration

		if self.getGlobalTimerDuration(gameConfig.TIMER_NAME_GLOBAL_LIMIT) > 0:
			status['timerGlobalStart'] = self.getGlobalTimerStart(gameConfig.TIMER_NAME_GLOBAL_LIMIT)
			status['timerGlobalDuration'] = self.getGlobalTimerDuration(gameConfig.TIMER_NAME_GLOBAL_LIMIT)

		# If the global time limit has run out, show FinalScene
		if self.getGlobalTimerEnd(gameConfig.TIMER_NAME_GLOBAL_LIMIT) > 0 and \
				int(timeStamp) >= self.getGlobalTimerEnd(gameConfig.TIMER_NAME_GLOBAL_LIMIT):
			status["phase"] = PhaseType.FinalScene

		# Return unlocked intro slides
		if(phase.name == PhaseType.ElementIntro):
			status["introProgress"] = self.introProgress
			status["introPos"] = self.introPos

		if phase.hasLevels():
			assert self.startedGame, "The game was not started"

			# If this phase has levels, send info about the level
			if phase.levelIdx in range(0, len(phase.levels)):
				level = phase.getLevel()
				status["levelName"] = level.fileName
				status["levelType"] = level.type
				status["taskIdx"] = phase.getNumTasks() - phase.getRemainingTasks() + 1
				status["numTasks"] = phase.getNumTasks()
				status["levelStart"] = level.getStartTime()

				# Check if level is dirty or has other server-defined state,
				# if yes send the current state
				if level.type == 'level':
					if level.isDirty():
						status["switchClicks"] = level.switchClicks
						status["confirmClicks"] = level.confirmClicks
						status["switches"] = level.getCurrentSwitchStates()
						status["solved"] = level.solved
					if level.hasRandomSwitches():
						status["switchOverride"] = level.getRandomSwitches()

			# Rare case: No levels remain after the player reloads the page
			else:
				if recursionBreaker:
					raise RuntimeError("/status could not be determined, recursion depth to big")
				
				self.nextPhase(int(timeStamp))
				status = self.status(timeStamp, recursionBreaker=True)
			
			assert status["levelName"] is not None and status["levelType"], "Panic, expected level but got None"
		
		# Increase the group counter, if the FinalScene is shown
		if status['phase'] == PhaseType.FinalScene and not self.startedFinal:
			self.startedFinal = True
			GroupStats.increasePlayersFinished(self.group, self.isDebug)

		return status


	def next(self, timeStamp: int):
		phase = self.getPhase()
		levelsRemain = phase.getRemainingLevels() > 1 and not self.failedQuali and not phase.timerHasEnded()
		pauseEnabled = self.getGlobalTimerEnd(gameConfig.TIMER_NAME_PAUSE) > 0

		self.logger.writeToLog(EventType.Click, '§Object: Continue Button', timeStamp)

		event = ClickEvent(
			clientTime=timeStamp, serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=None,
			object='Continue Button'
		)
		event.commit()

		# Insert Pause Slide if enabled, the time has come and at least one level remains
		if phase.hasLevels() and levelsRemain:
			if pauseEnabled and not self.pauseShown:
				if self.getGlobalTimerEnd(gameConfig.TIMER_NAME_PAUSE) < int(timeStamp):
					assert 'pause' in self.getGamerules(), "Missing key 'pause' in gamerules"
					path_pause_slide = 'pause/' + self.getGamerules()['pause'].get('fileName', gameConfig.DEFAULT_PAUSE_SLIDE)

					# NOTE We insert at the position of the current level, therefore the pause slide has
					# the same position as the current level. But the primary key will be higher and therefore
					# the database driver *should* sort it after the current level in the array aka levelIdx+1.
					phase.insertLevel(Level('special', path_pause_slide), phase.levelIdx)

					self.pauseShown = True
					db.session.commit() # We need to commit now, because otherwise Level attributes are not initialized

		# Start next Level if the phase got some and they are not finished
		if levelsRemain:
			phase.nextLevel(timeStamp)
		# Start next Phase
		else:
			self.nextPhase(timeStamp)

		assert self.startedGame, "The game was not started!"


	def chronograph(self, timeStamp: int, type: Any, id: Any, operation: Any, clientTime: Any, limit: Any = None):
		"""Centralized place to start and end different timers. 
		
		Take care to send the client time at the precise time as the accuracy depends on it.
		"""
		phase = self.getPhase()

		SUPPORTED_OPERATIONS = ["load", "start", "update", "stop"]
		if operation not in SUPPORTED_OPERATIONS:
			raise ValueError("Operation must be one of " + str(operation) + "!")

		event = ChronoEvent(
			clientTime=clientTime, serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=self.getLevelContext() if self.getPhase().hasLevels() else None,
			operation=operation,
			timerType=type,
			context=Level.uniformName(id),
			limit=limit
		)
		event.commit()

		if type in ALL_LEVEL_TYPES.keys():
			# Write the level start time to log
			try:
				if operation == "start":
					self.logger.writeToLog(EventType.LevelStarted, '§Type: ' + ALL_LEVEL_TYPES[str(type)], timeStamp)
					phase.getLevel().timerStart(timeStamp)

				elif operation == "stop":
					phase.getLevel().timerEnd(timeStamp)
			except Exception:
				raise JsonRPC_Error(JsonRPC_Errcode.I_INVALID_STATE, desc="No level is active")
		
		elif type == "phase":
			# Write the new Phase Event to log
			if operation == "start":
				self.logger.writeToLog(EventType.PhaseStarted, '§Phase: ' + self.getPhaseName(), timeStamp)

				# Save first start time (needed by pause screen)
				self.getPhase().timerStart(timeStamp)

		elif type == "countdown":
			# Start the phase time limit
			if operation == "start": phase.setFirstLevelTime(timeStamp)  # noqa: E701
			elif operation == "stop": phase.timerEnd(timeStamp) # noqa: E701

		elif type == "undefined":
			raise ValueError("The level is undefined, the game has probably crashed!")

		else:
			raise ValueError("Unknown parameter type for this timer!")


	def clickSwitch(self, 
			timeStamp: int, 
			id: Any, solved: Any, 
			s_switch: Any = None, s_bulb: Any = None, s_danger: Any = None, 
			s_not: Any = None, s_and: Any = None, s_or: Any = None
		):
		"""Called whenever a switch inside a circuit is toggled by the player.
		
		The full level circuit state will only be send by the game scene. In an InfoPanel, IntroduceElements or 
		IntroduceDrawingTools only `id` and `solved` are populated.
		"""
		phase = self.getPhase()

		e = '§Object: Switch'
		if s_switch is None and s_bulb is None:
			e += '\n§Solving State: ' + str(int(solved))
		else:
			e += '\n§Switch ID: ' + str(int(id)) + ', Level Solved: ' + str(int(solved))
			e += getCircuitStatusLog(s_switch, s_bulb, s_danger, s_not, s_and, s_or)

		self.logger.writeToLog(EventType.Click, e, timeStamp)

		levelState = LevelState(
			solved=solved in X_TRUE,
			s_switch=s_switch,
			s_bulb=s_bulb,
			s_danger=s_danger,
			s_not=s_not,
			s_and=s_and,
			s_or=s_or
		)

		event = SwitchClickEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=self.getLevelContext() if self.getPhase().hasLevels() else None,
			levelState=levelState,
			switchID=id
		)
		event.commit()
		
		# Try to update the level stats
		try:
			if phase.hasLevels() and s_switch is not None:
				phase.getLevel().switchClicks += 1
				phase.getLevel().updateSwitches(s_switch)
		except Exception:
			raise JsonRPC_Error(JsonRPC_Errcode.I_INVALID_STATE, desc="No level is active")


	def clickConfirm(self, 
			timeStamp: int, solved: Any, user: Any, 
			s_switch: Any = [], s_bulb: Any = [], s_danger: Any = [],
			s_not: Any = [], s_and: Any = [], s_or: Any = []
		):
		phase = self.getPhase()
		
		e = '§Object: ConfirmButton'
		e += '\n§Level Solved: ' + str(solved)
		e += '\n§User: ' + str(user)
		e += getCircuitStatusLog(s_switch, s_bulb, s_danger, s_not, s_and, s_or)
		self.logger.writeToLog(EventType.Click, e, timeStamp)

		# Try to update the level stats
		try:
			phase.getLevel().confirmClicks += 1
			phase.getLevel().solved = solved in X_TRUE
		except Exception:
			raise JsonRPC_Error(JsonRPC_Errcode.I_INVALID_STATE, desc="No level is active")
		
		levelState = LevelState(
			solved=phase.getLevel().solved,
			s_switch=s_switch,
			s_bulb=s_bulb,
			s_danger=s_danger,
			s_not=s_not,
			s_and=s_and,
			s_or=s_or
		)

		event = ConfirmClickEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level = self.getLevelContext(),
			levelState=levelState,
			user=user in X_TRUE
		)
		event.commit()


	def qualiStatus(self, timeStamp: int, failed: Any):
		phase = self.getPhase()
		lvlNo = phase.getNumTasks() - phase.getRemainingTasks() + 1
		qualified = not bool(failed)

		event = QualiEvent(
			clientTime=timeStamp, serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=self.getLevelContext(),
			qualified=qualified, ordinal=lvlNo
		)
		event.commit()

		if not qualified:
			self.failQuali()
			self.logger.writeToLog(EventType.QualiFailed + ParticipantLogger.getOrdinalNumber(lvlNo) + ' Quali Level', '', timeStamp)
		else:
			self.logger.writeToLog(EventType.QualiPassed + ParticipantLogger.getOrdinalNumber(lvlNo) + ' Quali Level', '', timeStamp)


	def popUp(self, timeStamp: int, content: Any, action: Any, a: Any = None, b: Any = None, c: Any = None):
		phase = self.getPhase()

		if action == 'hide':
			e = EventType.Click
			msg = '§Object: Pop-Up Button\n§Consequence Event: Pop-Up closed'

		elif action == 'show':
			e = EventType.PopUp
			msg = '§Content: '
			if content == "feedback":
				msg += 'Feedback about Clicks'
				msg += '\n§Nmbr Switch Clicks: ' + str(int(a))
				msg += '\n§Optimum Switch Clicks: ' + str(int(b))
				msg += '\n§Nmbr Confirm Clicks: ' + str(int(c))

			elif content == "timeRemaining":
				msg += 'Seconds remaining'
				msg += '\n§Seconds remaining: ' + str(int(a))

			elif content == "timerEnd":
				msg += 'Timer End'
				msg += '\n§Seconds remaining: 0'

			elif content == "introSkip":
				msg += 'Introducing Skip-Level Button'

			elif content == "introConfirm":
				msg += 'Explaining Confirm Button'

			elif content == "drawDemand":
				msg += 'Invitation to paint'

			elif content == "alreadyStarted":
				msg += 'Game already started'

			elif content == "levelTimerEnd":
				msg += 'Level Timer End'
				msg += '\n§Seconds remaining: 0'

			else:
				raise ValueError("Invalid value for content: \"" + content + "\"")
		
		else:
			raise ValueError("Invalid value for action: \"" + action + "\"")

		self.logger.writeToLog(e, msg, timeStamp)

		secondsRemaining = (a if content == "timeRemaining" 
			else a if content == "timerEnd" else None)
		
		nmbrSwitchClicks = a if content == "feedback" else None

		event = PopUpEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=self.getLevelContext(),
			dialogName=content,
			action=(action == 'show'),
			nmbrSwitchClicks=nmbrSwitchClicks,
			optimumSwitchClicks=b,
			nmbrConfirmClicks=c,
			secondsRemaining=secondsRemaining
		)
		event.commit()

		# Try to update the level stats
		if action=="show" and content=="feedback":
			try:
				level = phase.getLevel()
				oldSwitchClicks = level.switchClicks
				oldMinSwitchClicks = level.minSwitchClicks # type: ignore
				oldConfirmClicks = level.confirmClicks

				level.switchClicks = int(a)
				level.minSwitchClicks = int(b)
				level.confirmClicks = int(c)

				# Safety checks: Alert when something seems off with the clicks
				assert level.switchClicks >= level.minSwitchClicks, \
					f"switchClicks >= minSwitchClicks ({level.switchClicks}, {level.minSwitchClicks})"
				assert level.confirmClicks > 0, \
					f"confirmClicks > 0 ({level.confirmClicks})"
				assert oldSwitchClicks == level.switchClicks, \
					f"oldSwitchClicks == switchClicks ({oldSwitchClicks}, {level.switchClicks})"
				assert oldMinSwitchClicks in [None, -1] or oldMinSwitchClicks == level.minSwitchClicks, \
					f"oldMinSwitchClicks == minSwitchClicks ({oldMinSwitchClicks}, {level.minSwitchClicks})" # There is no oldMinSwitchClicks on first try
				assert oldConfirmClicks == level.confirmClicks, \
					f"oldConfirmClicks == confirmClicks ({oldConfirmClicks}, {level.confirmClicks})"

			except AssertionError as msg:
				print(f"{self.pseudonym}: Assertion failed: " + str(msg), file=sys.stderr)

			except Exception:
				raise JsonRPC_Error(JsonRPC_Errcode.I_INVALID_STATE, desc="Invalid level state")


	def selectDrawingTool(self, timeStamp: int, tool: Any):
		if tool in ['Red', 'Green', 'Blue']:
			e = '§Object: Brush'
			e += '\n§Color: ' + str(tool)
		elif tool in ['Eraser', 'Delete Button']:
			e = '§Object: ' + str(tool)
		else:
			raise ValueError("Unknown tool \"" + tool + "\"")

		self.logger.writeToLog(EventType.Click, e, timeStamp)

		event = SelectDrawToolEvent(
			clientTime=timeStamp, serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=self.getLevelContext(),
			object=tool
		)
		event.commit()


	def useDrawingTool(self, timeStamp: int, tool: Any, info: Any = None):
		event = DrawEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=self.getLevelContext() if self.getPhase().hasLevels() else None,
			tool=tool,
			info=info
		)
		event.commit()

		if tool == 'pen':
			e = EventType.Pen
			msg = '§Color: ' + str(int(info))
		elif tool == 'eraser':
			e = EventType.DrawingTool
			msg = '§Tool: eraser'
		elif tool == 'purge':
			e = EventType.DrawingTool
			msg = '§Tool: delete button'
		else:
			raise ValueError("Unknown tool \"" + tool + "\"")
		
		self.logger.writeToLog(e, msg, timeStamp)

	
	def skipLevel(self, timeStamp: int):
		phase = self.getPhase()
		
		self.logger.writeToLog(EventType.Click, '§Object: Skip-Level Button\n§Consequence Event: Current level is being skipped', timeStamp)

		event = ClickEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=self.getLevelContext(),
			object='Skip-Level Button'
		) # TODO Maybe add level state here?
		event.commit()

		# Try to update the level stats
		try:
			phase.getLevel().timerEnd(timeStamp)
			phase.getLevel().skipped = True
		except Exception:
			raise JsonRPC_Error(JsonRPC_Errcode.I_INVALID_STATE, desc="No level is active")

	
	def simulate(self, timeStamp: int, status: Any, user: Any):
		"""`status` is True, if Wires are shown and False otherwise"""
		if bool(status):
			self.logger.writeToLog(EventType.Click, '§Object: Simulate-Level Button\n§Consequence Event: Show power', timeStamp)
		else:
			self.logger.writeToLog(EventType.Click, '§Object: Simulate-Level Button\n§Consequence Event: Hide power', timeStamp)

		event = SimulateEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=self.getLevelContext(),
			showPower=status
		)
		event.commit()


	def slide(self, timeStamp: int, type: Any, label: Any, direction: Any):
		NUM_INTRO_LABELS = len(IntroLabels)

		try:
			delta = int(direction)
			assert delta in range(-NUM_INTRO_LABELS, NUM_INTRO_LABELS)
		except Exception:
			raise JsonRPC_Error(JsonRPC_Errcode.INVALID_PARAMS, desc="invalid value for direction")

		if type in ['Description', 'Challenge'] and label in IntroLabels:
			# Write event log and adjust server state
			self.logger.writeToLog(EventType.Click, '§Object: Arrow\n§Box: ' + str(label) + '\n§Box Type: ' + str(type), timeStamp)
			self.introPos = self.introPos + delta
			self.introProgress = max(self.introProgress, self.introPos)
		else:
			pass # TODO FIXME
			#raise JsonRPC_Error(JsonRPC_Errcode.INVALID_PARAMS, desc="type or label invalid")
		
		event = IntroNavigationEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			currentSlide=self.introPos,
			isChallenge=(type == 'Challenge'),
			label=label,
			delta=delta
		)
		event.commit()


	def changeLanguage(self, timeStamp: int, lang: Any):
		self.logger.writeToLog(EventType.Click, '§Object: Language Button\n§Language: ' + str(lang).upper()[:2], timeStamp)

		event = LanguageSelectionEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			language=lang
		)
		event.commit()


	def sessionState(self, timeStamp: int):
		"""Called in the PreloadScene to determine if the game is already running or if this is the first session"""
		self.logger.writeToLog(EventType.StartSession, '', timeStamp)

		state = {
			'scene': self.getPhaseName() if self.startedGame else 'not started',
			'firstSession': 'yes' if self.packetIndex == 0 else 'no',
		}

		event = StartSessionEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase=state['scene'],
			packetIndex=self.packetIndex
		)
		event.commit()

		return state


	def altTask(self, timeStamp: int, a: Any, b: Any):
		if not self.getPhaseName() == PhaseType.AltTask:
			raise JsonRPC_Error(JsonRPC_Errcode.I_INVALID_STATE, desc="Not in AltTask")

		param_a = str(a)[:32].strip()
		param_b = str(b)[:16].strip()

		# Only allow alphabetic character for param_a and alpha-numeric characters for param_b
		if not (param_a.replace(' ', '').isalpha() and param_b.replace(' ', '').isalnum()):
			raise ValueError("a/b must only contain letters from the alphabet")
		
		self.logger.writeToLog(EventType.AltTask, '§' + param_a + ': ' + param_b, timeStamp)

		event = AltTaskEvent(
			clientTime=timeStamp,
			serverTime=now(),
			pseudonym=self.pseudonym,
			phase=self.getPhaseName(),
			level=self.getLevelContext(),
			param_key=param_a,
			param_val=param_b
		)
		event.commit()


	def checkTimeDrift(self, clientTime: int, serverTime: int):
		"""Compare the client and server time and write a log entry if they deviate too much. 
		To prevent spamming the logfile, a log is only written if the stored delta deviates. This also compensates
		if the client time is in a different time zone. 
		"""
		currentDelta = serverTime - clientTime

		if self.timeDelta is None or abs(currentDelta - self.timeDelta) > gameConfig.TIME_DRIFT_THRESHOLD: # default: 100ms
			self.timeDelta = currentDelta
			self.logger.writeToLog(EventType.TimeSync, '§Server: ' + str(serverTime), clientTime)


	def getGlobalTimerStart(self, configName: str) -> int:
		"""Get the time at which the global timer was started in millis.
		
		supported values for `configName` as of now are:
		  - `config.TIMER_NAME_PAUSE`
		  - `config.TIMER_NAME_GLOBAL_LIMIT`

		-1: Timer not started
		-2: Timer disabled
		"""
		# Return -2 if timer is not enabled
		if configName not in self.getGamerules():
			return -2
		
		# Use the Phase name specified in `startEvent` or default to the first Phase as the timer beginning.
		TIMER_SETTINGS = self.getGamerules()[configName]
		START_PHASE = self.getConfig()['phases'][0] if TIMER_SETTINGS['startEvent'] is None \
			else TIMER_SETTINGS['startEvent']
		
		# Find the first Phase where the start event matches the phase name or return -1 if none is found
		return next((p.timeStarted for p in self.phases if p.name == START_PHASE), -1)


	def getGlobalTimerDuration(self, configName: str) -> int:
		"""Get the duration of a global timer in millis. 

		supported values for `configName` as of now are:
		  - `config.TIMER_NAME_PAUSE`
		  - `config.TIMER_NAME_GLOBAL_LIMIT`

		-1: Timer not started
		-2: Timer disabled
		-6: Duration too small
		"""
		# Return -2 if timer is not enabled
		if configName not in self.getGamerules():
			return -2
		
		TIMER_DURATION = self.getGamerules()[configName]['after']
		
		if TIMER_DURATION < 0.1:
			return -6

		# True if the timer since `startEvent` has run out, false otherwise
		return TIMER_DURATION * 1000
	

	def getGlobalTimerEnd(self, configName: str) -> int:
		timerStart = self.getGlobalTimerStart(configName)
		timerDuration = self.getGlobalTimerDuration(configName)

		if timerStart < 0:
			return timerStart
		elif timerDuration < 0:
			return timerDuration

		return timerStart + timerDuration


	# ---------------------

	@staticmethod
	def convertPhaseIndex(groupName: str, phaseIdx: int) -> str:
		return gameConfig.getGroup(groupName)['phases'][phaseIdx]


	@staticmethod
	def createGroup(group: str) -> Tuple[str, bool]:
		"""Assert that the group actually exists and remove the debug prefix"""
		strippedGroup = group.casefold()
		isDebug = False

		if (len(group) > 5
			and strippedGroup.startswith('debug') 
			and strippedGroup not in gameConfig.groups()
		):
			strippedGroup = strippedGroup.removeprefix('debug')
			isDebug = True

		try: 
			gameConfig.getGroup(strippedGroup)
		except Exception:
			raise ModelFormatError(f'The group {strippedGroup} is unknown (unparsed group: {group})')

		return strippedGroup, isDebug
