from datetime import datetime, timezone
import logging
import math
import os
from typing import Any, Callable, Union

from markupsafe import Markup

from app.gameConfig import ALL_LEVEL_TYPES, LOGFILE_VERSION, TIME_DRIFT_THRESHOLD
from app.model.LogEvents import (
	AltTaskEvent,
	ChronoEvent,
	ClickEvent,
	ConfirmClickEvent,
	DrawEvent,
	GameOverEvent,
	GroupAssignmentEvent,
	IntroNavigationEvent,
	LanguageSelectionEvent,
	LogCreatedEvent,
	LogEvent,
	PopUpEvent,
	QualiEvent,
	ReconnectEvent,
	RedirectEvent,
	SelectDrawToolEvent,
	SimulateEvent,
	SkillAssessmentEvent,
	StartSessionEvent,
	SwitchClickEvent,
)
from app.utilsGame import (
	ClickableObjects,
	EventType,
	LogKeys,
	PhaseType,
	ServerTimeEvents,
	gateStatesToString,
	getCircuitStatusLog,
	now,
	safe_join,
)

import app.config as gameConfig


LOG_ENCODING = "UTF-8"


class ParticipantLogger:
	"""Legacy Logger that writes to plaintext files"""

	baseFolder = "instance/statistics/LogFiles"

	def __init__(self, pseudonym: str, loggingEnabled: bool):
		self.EVENT_MAP: dict[str, Callable[[LogEvent], Any]] = { # type: ignore
			LogCreatedEvent.__name__: self.logCreation,
			LanguageSelectionEvent.__name__: self.logLanguageSelection,
			GroupAssignmentEvent.__name__: self.logGroupAssignment,
			RedirectEvent.__name__: self.logRedirect,
			ReconnectEvent.__name__: self.logBackOnline,
			GameOverEvent.__name__: self.logGameEnd,
			ChronoEvent.__name__: self.chronoEvent,
			StartSessionEvent.__name__: self.logSessionStart,
			SkillAssessmentEvent.__name__: self.logSkillAssessment,
			QualiEvent.__name__: self.logQualiCondition,
			ClickEvent.__name__: self.clickEvent,
			SwitchClickEvent.__name__: self.logSwitchClick,
			ConfirmClickEvent.__name__: self.logConfirmClick,
			SimulateEvent.__name__: self.logSimulation,
			IntroNavigationEvent.__name__: self.logIntroNavigation,
			SelectDrawToolEvent.__name__: self.logDrawToolSelect,
			DrawEvent.__name__: self.logDrawCall,
			PopUpEvent.__name__: self.logPopup,
			AltTaskEvent.__name__: self.logAltTask,
		}
	
		self.pseudonym = pseudonym
		self.loggingEnabled = loggingEnabled
		self.logPath = ParticipantLogger.getLogfilePath(pseudonym)
		self.timeDelta: int|None = None


	def chronoEvent(self, event: ChronoEvent) -> str:
		""""""
		assert event.phase is not None
		if event.phase.activePhase == PhaseType.Preload:
			return self.logPreload(event)

		if event.timerType in ALL_LEVEL_TYPES.keys():
			assert event.level is not None
			if event.operation == "load":
				return self.logNewLevel(
					timeStamp=self.toUnix(event.timeClient),
					levelTypeLog=ALL_LEVEL_TYPES[event.level.levelType],
					fileName=event.level.levelName,
					randomSwitches=ParticipantLogger.extractRandomSwitches(event)
				)

			elif event.operation == "start":
				return self.logLevelStarted(event)
			
			elif event.operation == "stop":
				return ""

		elif event.timerType == "phase":
			assert event.phase is not None
			if event.operation == "load":
				return self.logNewPhase(
					timeStamp=self.toUnix(event.timeClient),
					scene=event.phase.activePhase
				)

			elif event.operation == "start":
				return self.logPhaseStarted(event)

		elif event.timerType == "countdown":
			return ""
		
		raise AssertionError(f'Unexpected timer type "{event.timerType}" or operation "{event.operation}"')


	def clickEvent(self, event: ClickEvent) -> str:
		if event.object == ClickableObjects.SKIP:
			return self.logSkip(event)
		elif event.object == ClickableObjects.CONTINUE:
			return self.logContinue(event)

		raise AssertionError(f'Unknown clickable object {event.object}')


	def nop(self, event: LogEvent) -> str:
		"""NO Operation, this event is not serialized"""
		logging.debug(f'Skipping {event}')
		return ""


	def logCreation(self, event: LogCreatedEvent) -> str:
		if self.loggingEnabled:
			return ParticipantLogger.createLogfile(self.pseudonym, self.logPath)

		return ParticipantLogger.getLogfileHeader(event.pseudonym)


	def logSkillAssessment(self, event: SkillAssessmentEvent) -> str:
		timeServer = self.toUnix(event.timeServer)
		return self.writeToLog(EventType.SkillAssessment, "§Score: " + str(event.score), timeServer)


	def logGroupAssignment(self, event: GroupAssignmentEvent) -> str:
		serverTime = self.toUnix(event.timeServer)
		msg = '§Group: ' + event.group
		return self.writeToLog(EventType.GroupAssignment, msg, serverTime)


	def logPreload(self, event: ChronoEvent) -> str:
		clientTime = self.toUnix(event.timeClient)
		return self.writeToLog(EventType.PhaseRequested, '§Scene: PreloadScene', clientTime)


	def logContinue(self, event: ClickEvent) -> str:
		clientTime = self.toUnix(event.timeClient)
		return self.writeToLog(EventType.Click, '§Object: Continue Button', clientTime)


	def logLevelStarted(self, event: ChronoEvent) -> str:
		assert event.level is not None
		clientTime = self.toUnix(event.timeClient)
		
		return self.writeToLog(EventType.LevelStarted, '§Type: ' + ALL_LEVEL_TYPES[str(event.level.levelType)], clientTime)


	def logPhaseStarted(self, event: ChronoEvent) -> str:
		assert event.phase is not None
		clientTime = self.toUnix(event.timeClient)
		return self.writeToLog(EventType.PhaseStarted, '§Phase: ' + event.phase.activePhase, clientTime)


	def logSwitchClick(self, event: SwitchClickEvent) -> str:
		assert event.levelState is not None
		clientTime = self.toUnix(event.timeClient)
		solved = event.levelState.solved
		s_switch = event.levelState.s_switch
		s_bulb = event.levelState.s_bulb
		s_danger = event.levelState.s_danger
		s_not = event.levelState.s_not
		s_and = event.levelState.s_and
		s_or = event.levelState.s_or

		# The ElementIntro or IntroDrawTools don't send full circuit states, only `solved`.
		# `s_switch` will always be send even if it would be an empty array, the rest are
		# omitted when the array is empty and therefore might be None. 
		# See `Circuit.json@getElementStatesJson()`
		not_a_full_level = s_switch is None #and s_bulb is None and s_danger is None

		e = '§Object: Switch'
		if not_a_full_level:
			e += '\n§Solving State: ' + str(int(event.levelState.solved))
		else:
			e += '\n§Switch ID: ' + str(event.switchID) + ', Level Solved: ' + str(int(solved))
			e += getCircuitStatusLog(s_switch, s_bulb, s_danger, s_not, s_and, s_or)

		return self.writeToLog(EventType.Click, e, clientTime)


	def logConfirmClick(self, event: ConfirmClickEvent) -> str:
		assert event.levelState is not None		
		clientTime = self.toUnix(event.timeClient)
		solved = event.levelState.solved
		s_switch = event.levelState.s_switch
		s_bulb = event.levelState.s_bulb
		s_danger = event.levelState.s_danger
		s_not = event.levelState.s_not
		s_and = event.levelState.s_and
		s_or = event.levelState.s_or

		e = '§Object: ConfirmButton'
		e += '\n§Level Solved: ' + str(int(solved))
		e += '\n§User: ' + (str(1) if event.user else str(0))
		e += getCircuitStatusLog(s_switch, s_bulb, s_danger, s_not, s_and, s_or)
		return self.writeToLog(EventType.Click, e, clientTime)


	def logQualiCondition(self, event: QualiEvent) -> str:
		assert isinstance(event.ordinal, int)
		clientTime = self.toUnix(event.timeClient)
		lvlNo = event.ordinal

		if not event.qualified:
			return self.writeToLog(EventType.QualiFailed + ParticipantLogger.getOrdinalNumber(lvlNo) + ' Quali Level', '', clientTime)
		else:
			return self.writeToLog(EventType.QualiPassed + ParticipantLogger.getOrdinalNumber(lvlNo) + ' Quali Level', '', clientTime)


	def logPopup(self, event: PopUpEvent) -> str:
		clientTime = self.toUnix(event.timeClient)
		action = 'show' if event.action else 'hide'
		content = event.dialogName

		if action == 'hide':
			e = EventType.Click
			msg = '§Object: Pop-Up Button\n§Consequence Event: Pop-Up closed'

		elif action == 'show':
			e = EventType.PopUp
			msg = '§Content: '
			if content == "feedback":
				assert event.nmbrSwitchClicks is not None and event.nmbrSwitchClicks >= 0
				assert event.optimumSwitchClicks is not None and event.optimumSwitchClicks >= 0
				assert event.nmbrConfirmClicks is not None and event.nmbrConfirmClicks > 0
				msg += 'Feedback about Clicks'
				msg += '\n§Nmbr Switch Clicks: ' + str(int(event.nmbrSwitchClicks))
				msg += '\n§Optimum Switch Clicks: ' + str(int(event.optimumSwitchClicks))
				msg += '\n§Nmbr Confirm Clicks: ' + str(int(event.nmbrConfirmClicks))

			elif content == "timeRemaining":
				assert event.secondsRemaining is not None and event.secondsRemaining >= 0
				msg += 'Seconds remaining'
				msg += '\n§Seconds remaining: ' + str(int(event.secondsRemaining))

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

		return self.writeToLog(e, msg, clientTime)


	# SelectDrawToolEvent
	def logDrawToolSelect(self, event: SelectDrawToolEvent):
		clientTime = self.toUnix(event.timeClient)
		assert isinstance(event.object, ClickableObjects)
		object = event.object

		BRUSHES = [
			ClickableObjects.PEN_RED, 
			ClickableObjects.PEN_GREEN, 
			ClickableObjects.PEN_BLUE
		]

		if object in BRUSHES:
			e = '§Object: Brush'
			e += '\n§Color: ' + str(object)
		elif object in [ClickableObjects.ERASER, ClickableObjects.DELETE]:
			e = '§Object: ' + str(object)
		else:
			raise ValueError("Unknown tool \"" + object + "\"")
		
		return self.writeToLog(EventType.Click, e, clientTime)


	def logDrawCall(self, event: DrawEvent) -> str:
		clientTime = self.toUnix(event.timeClient)
		tool = event.tool
		info = event.color

		if tool == 'pen':
			e = EventType.Pen
			msg = '§Color: ' + str(info)
		elif tool == 'eraser':
			e = EventType.DrawingTool
			msg = '§Tool: eraser'
		elif tool == 'purge':
			e = EventType.DrawingTool
			msg = '§Tool: delete button'
		else:
			raise ValueError("Unknown tool \"" + tool + "\"")
		
		return self.writeToLog(e, msg, clientTime)


	def logSkip(self, event: ClickEvent):
		clientTime = self.toUnix(event.timeClient)
		return self.writeToLog(EventType.Click, '§Object: Skip-Level Button\n§Consequence Event: Current level is being skipped', clientTime)


	def logSimulation(self, event: SimulateEvent) -> str:
		clientTime = self.toUnix(event.timeClient)

		if bool(event.showPower):
			return self.writeToLog(EventType.Click, '§Object: Simulate-Level Button\n§Consequence Event: Show power', clientTime)
		else:
			return self.writeToLog(EventType.Click, '§Object: Simulate-Level Button\n§Consequence Event: Hide power', clientTime)


	def logIntroNavigation(self, event: IntroNavigationEvent) -> str:
		clientTime = self.toUnix(event.timeClient)
		label = event.label
		boxType = "Challenge" if event.isChallenge else "Description"
		assert len(label) > 0

		return self.writeToLog(EventType.Click, '§Object: Arrow\n§Box: ' + str(label) + '\n§Box Type: ' + str(boxType), clientTime)


	def logLanguageSelection(self, event: LanguageSelectionEvent) -> str:
		clientTime = self.toUnix(event.timeClient)
		lang = str(event.language).upper()[:2]

		return self.writeToLog(EventType.Click, '§Object: Language Button\n§Language: ' + lang, clientTime)


	def logSessionStart(self, event: StartSessionEvent) -> str:
		clientTime = self.toUnix(event.timeClient)
		return self.writeToLog(EventType.StartSession, '', clientTime)

	
	def logAltTask(self, event: AltTaskEvent) -> str:
		clientTime = self.toUnix(event.timeClient)
		param_a = event.param_key
		param_b = event.param_val

		return self.writeToLog(EventType.AltTask, '§' + param_a + ': ' + param_b, clientTime)


	def logTimeDrift(self, clientTime: int, serverTime: int) -> str:
		return self.writeToLog(EventType.TimeSync, '§Server: ' + str(serverTime), clientTime)
	

	def logRedirect(self, event: RedirectEvent) -> str:
		serverTime = self.toUnix(event.timeServer)
		msg1 = '§Destination: ' + event.destination
		return self.writeToLog(EventType.Redirect, msg1, serverTime)
		

	def logBackOnline(self, event: ReconnectEvent):
		clientTime = self.toUnix(event.timeClient)
		elapsed = event.elapsed
		return self.writeToLog(EventType.BackOnline, '§Duration[s]: ' + str(elapsed), clientTime)

	
	def logGameEnd(self, event: GameOverEvent):
		clientTime = self.toUnix(event.timeServer)
		return self.writeToLog(EventType.GameOver, '', clientTime)


#####################################################################


	def prepareLogEvent(self, event: str, msg: str, timeStamp: Any):
		# Sanitize and unescape 
		if isinstance(msg, Markup):
			msg = str(msg)

		# Make sure the event body is well formatted
		msg = msg.strip()
		if len(msg) > 0:
			msg = '\n' + msg

		fullMessage = "\n§Event: " + event.strip() + msg

		isServerTime = event in ServerTimeEvents
		timeline = (LogKeys.TIME_SERVER if isServerTime else LogKeys.TIME) + ": " + str(timeStamp)
		return '\n' + timeline + fullMessage + '\n' # write to log file adding a timestamp


	# write to log file adding a timestamp
	def writeToLog(self, event: str, msg: str, timeStamp: Union[str, int]) -> str:
		"""Append a log entry to the ui specific logfile. """
		message = self.prepareLogEvent(event=event, msg=msg, timeStamp=timeStamp)

		# Make sure, that even if the player where to send something, it is dropped
		if self.loggingEnabled:
			self.writeToDisk(message=message, logPath=self.logPath, create=False)
		
		return message
	

	def checkTimeDelta(self, clientTime: datetime, serverTime: datetime):
		clientTimestamp = self.toUnix(clientTime)
		serverTimestamp = self.toUnix(serverTime)
		currentDelta = serverTimestamp - clientTimestamp

		if self.timeDelta is None or abs(currentDelta - self.timeDelta) > TIME_DRIFT_THRESHOLD: # default: 100ms
			self.timeDelta = currentDelta
			
			return self.logTimeDrift(clientTime=clientTimestamp, serverTime=serverTimestamp)
		
		return None


	@staticmethod
	def writeToDisk(message: str, logPath: str, create: bool):
		with open(logPath, 'tx' if create else 'ta', encoding=LOG_ENCODING) as f:
			return f.write(message)
		
		return 0


	def logNewPhase(self, timeStamp: Union[str, int], scene: str):
		return self.writeToLog(EventType.PhaseRequested, '§Scene: ' + scene, timeStamp)


	def logNewLevel(self, timeStamp: Union[str, int], levelTypeLog: str, fileName: str, randomSwitches: dict[str, int]):
		if len(randomSwitches) > 0:
			stringifiedArray = gateStatesToString(randomSwitches)
			randomSwitchesText = '\n§RandomSwitches [ID, outputstate]: ' + stringifiedArray
		else:
			randomSwitchesText = ''
			
		return self.writeToLog(
			EventType.LevelRequested + levelTypeLog,
			'§Filename: ' + fileName +
			randomSwitchesText, timeStamp
		)


	@classmethod
	def getLogfilePath(cls, pseudonym: str) -> str:
		return safe_join(cls.baseFolder, "logFile_" + pseudonym + ".txt")


	@staticmethod
	def getLogfileHeader(pseudonym: str) -> str:
		msg = "\n§Event: " + EventType.CreatedLog + "\n§Version: " + LOGFILE_VERSION + "\n§Pseudonym: " + pseudonym + \
				"\n§GitHashS: " + gameConfig.getGitHash()

		timeline = LogKeys.TIME_SERVER + ": " + str(now())
		return '\n' + timeline + msg + '\n' # write to log file adding a timestamp


	@staticmethod
	def createLogfile(pseudonym: str, logPath: str|None = None) -> str:
		"""Create a logfile for the specified pseudonym."""
		if logPath is None:
			logPath = ParticipantLogger.getLogfilePath(pseudonym)

		try:
			# NOTE Pythons umask is weird by default, it can't read the files it just created
			os.umask(0o002)
			
			message = ParticipantLogger.getLogfileHeader(pseudonym)
			ParticipantLogger.writeToDisk(
				message=message,
				logPath=logPath,
				create=True
			)
			return message

		# Min Python Version so that open will Raise FileExistsError in 'x' mode: 3.3
		except FileExistsError:
			raise PseudonymCollision("The pseudonym " + pseudonym + " already exists!")


	@staticmethod
	def toUnix(timestamp: Any, assumeUTC: bool = True) -> int:
		"""Convert the datetime object to a POSIX timestamp in milliseconds since 1.1.1970

		assumeUTC: When set to false, "naive" datetime objects (missing tz information)
		will be treated as local time. However when you construct your datetime object 
		from a POSIX timestamp this would lead to an offset.
		"""
		assert isinstance(timestamp, datetime)

		if timestamp.tzinfo is None and assumeUTC:
			timestamp = timestamp.replace(tzinfo=timezone.utc)

		return math.floor(timestamp.timestamp() * 1000)

	
	@staticmethod
	def getOrdinalNumber(i: int) -> str:
		NUMBER_WORDS = ['0th', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth']
		if i in range(0, len(NUMBER_WORDS)):
			return NUMBER_WORDS[i]
		else:
			return str(i) + 'th'


	@staticmethod
	def extractRandomSwitches(event: ChronoEvent) -> dict[str, int]:
		if event.annex is None:
			return {}

		return event.annex.get("randSwitches", {})


class PseudonymCollision(ValueError):
	"""The passed pseudonym already exists."""
	pass
