from datetime import datetime
from typing import Any, Dict, List, Optional, Union, cast

from app.model.Level import ALL_LEVEL_TYPES, LEVEL_FILETYPES_WITH_TASK, REMAP_LEVEL_TYPES
from app.statistics.staticConfig import EVENT_T, LevelStatus
from app.statistics.statisticUtils import TIME_NONE, LogSyntaxError, calculateDuration, calculateIES
from app.statistics.staticConfig import ENABLE_SPECIAL_CASES
from app.utilsGame import X_TRUE, X_FALSE

LEVEL_ATTRIB_T = Dict[str, Union[bool, int, LevelStatus, datetime]]

class StatsLevel():
	def __init__(self, type: str, name: str) -> None:
		self.stats = StatsLevel.createStatsLevel()

		if ENABLE_SPECIAL_CASES:
			self.oldAttempts: List[LEVEL_ATTRIB_T] = [] # TODO: Since milestone6 there is no need to store old runs

		# Remap text to info
		if type in REMAP_LEVEL_TYPES:
			type = REMAP_LEVEL_TYPES[type]

		# Make sure the level type is known to this script
		if type not in ALL_LEVEL_TYPES:
			raise LogSyntaxError("Unknown level type: " + type + "!")

		self.type = type
		self.name = name

		# The position of each task will be different for each participant if shuffle is turned on
		self.position = -1

		# Set to true after a reconnect
		self.reloadFlag = False


	def post(self, event: Optional[EVENT_T]):
		"""Called at the end of each level (before the next level)
		
		You can call this method multiple times without damage.
		"""
		# Non task levels have no confirm click that will set the level to `SOLVED`
		# NOTE This means no Status `ABORTED` or `NOTREACHED` for info screens, tutorials etc.
		if not self.isTask():
			self.stats['status'] = LevelStatus.SOLVED

		# Change the current state to the final states for the CSV
		if self.stats['status'] == LevelStatus.INPROGRESS:
			self.stats['status'] = LevelStatus.ABORTED
		elif self.stats['status'] in [LevelStatus.NOTSTARTED, LevelStatus.LOADED]:
			self.stats['status'] = LevelStatus.NOTREACHED

		# Set end time
		if event is not None:
			assert isinstance(event['Time'], datetime)
			self.stats['unloadTime'] = event['Time']


	def isTask(self) -> bool:
		return self.type in LEVEL_FILETYPES_WITH_TASK


	def onLoad(self, event: EVENT_T, position: int):
		"""Event: Called after the level is loaded (the first of the two events with the filename)"""
		assert isinstance(self.stats['status'], LevelStatus)
		assert not position < 0

		if self.stats['status'] != LevelStatus.NOTSTARTED:
			raise LogSyntaxError("Invalid level status on load: " + self.stats['status'].name + " for level " + self.name + "!")

		self.position = position
		self.stats['status'] = LevelStatus.LOADED


	def onStart(self, event: EVENT_T):
		"""Event: Called after the level is shown to the player. (the second of the two events with just loaded in the event data)"""
		assert isinstance(event['Time'], datetime)
		assert isinstance(self.stats['status'], LevelStatus)

		# Complain if eventType does not match
		if event['Type'] != ALL_LEVEL_TYPES[self.type]:
			raise LogSyntaxError("Type mismatch when starting level!")

		# Check preconditions if the level is loaded (skip this check on reconnects)
		if not self.reloadFlag:
			if self.stats['status'] != LevelStatus.LOADED:
				raise LogSyntaxError("Invalid level status on start: " + self.stats['status'].name + " for level " + self.name + "!")

		# Can only be false after a page reload if the level load event was send before the reload.
		if self.stats['status'] == LevelStatus.LOADED:
			# Set the start time if this is the first load
			self.stats['startTime'] = event['Time']
			self.stats['firstTryTime'] = event['Time']

			# Update the state from loaded to in progress
			self.stats['status'] = LevelStatus.INPROGRESS

		# Reset the reload flag
		self.reloadFlag = False
		pass


	def onSwitchClick(self, event: EVENT_T):
		"""Event: Fired after the user clicked a switch.
		
		This method will bump the end timer!
		"""
		assert isinstance(self.stats['switchClicks'], int)

		# Check precondition
		if self.type not in FILE_TYPES_WITH_SWITCHES:
			raise LogSyntaxError("Switch click in a level without a circuit.")

		self.onInteraction(event)
		
		self.stats['switchClicks'] += 1


	def onConfirmClick(self, event: EVENT_T):
		"""Event: Fired after the user presses the confirm button
		
		If the client reports, that this level was solved correctly, change the level status. Otherwise, 
		increase the server side confirm click counter.

		This method will bump the end timer!
		"""
		assert isinstance(self.stats['confirmClicks'], int)
		assert 'Level Solved' in event and isinstance(event['Level Solved'], str)
		assert event['Level Solved'].casefold() in X_TRUE+X_FALSE # NOTE True and False are 0 and 1 in older logfile versions

		# Check preconditions
		if self.type != 'level':
			raise LogSyntaxError("Confirm click in a level without a circuit.")

		self.onInteraction(event)
		solvingStatus: bool = event['Level Solved'].casefold() in X_TRUE
		
		# Stop first try timer
		if self.stats['confirmClicks'] < 1:
			self.stats['firstTryTime'] = event['Time']

		# NOTE Always increment the confirm clicks
		self.stats['confirmClicks'] += 1

		# Level is solved
		if solvingStatus:
			self.stats['status'] = LevelStatus.SOLVED


	def onLevelSolvedDialogue(self, event: EVENT_T):
		"""Event: Fired after the level feedback dialogue is shown.
		
		Sanity check the client switch/confirm clicks against the ones recognized by the server. 
		The minimum switch clicks necessary are only calculated by the client and are therefore also read in this step.

		This method will bump the end timer!
		"""
		assert isinstance(self.stats['switchClicks'], int)
		assert isinstance(self.stats['skipped'], bool)

		# Check preconditions
		if self.type != 'level':
			raise LogSyntaxError("Level solved dialogue in a level without a circuit.")

		self.stats['feedback'] = True
		self.stats['minSwitchClicks'] = int(event["Optimum Switch Clicks"])
		self.stats['endTime'] = event['Time']

		if self.stats['endTime'] < self.stats['startTime']:
			raise LogSyntaxError("Level start time " + str(self.stats['startTime']) + " should be before end time " \
					+ str(self.stats['endTime']) + "!")

		if self.stats['switchClicks'] != int(event["Nmbr Switch Clicks"]):
			raise LogSyntaxError("Discrepancy in switch clicks: Server recorded " + str(self.stats['switchClicks']) \
					+ ", client send " + str(int(event["Nmbr Switch Clicks"])) + "!")

		if self.stats['confirmClicks'] != int(event["Nmbr Confirm Clicks"]):
			raise LogSyntaxError("Discrepancy in confirm clicks: Server recorded " + \
					str(self.stats['confirmClicks']) + ", client send " + str(int(event["Nmbr Confirm Clicks"])) \
					+ "!")

		if self.stats['switchClicks'] < self.stats['minSwitchClicks'] \
				and not self.stats['skipped'] \
				and not self.stats['status'] == LevelStatus.FAILED:
			
			raise LogSyntaxError("Somehow the user managed to click fewer switches than required!")


	def onSkip(self, event: EVENT_T):
		"""Event: Fired after the player is skipping this level.
		
		This method will bump the end timer!
		"""
		self.onInteraction(event)

		self.stats['status'] = LevelStatus.SKIPPED
		self.stats['skipped'] = True
		self.stats['endTime'] = event['Time']

		if self.stats['endTime'] < self.stats['startTime']:
			raise LogSyntaxError("Level start time " + str(self.stats['startTime']) + " should be before end time " + str(self.stats['endTime']) + "!")


	def onInteraction(self, event: EVENT_T, check: bool = True):
		"""Called when the player is interacting with switches, buttons, drawing tools etc."""
		assert isinstance(self.stats['status'], LevelStatus)
		assert isinstance(self.stats['startTime'], datetime)
		assert isinstance(event['Time'], datetime)

		# Check preconditions
		if check and self.stats['status'] not in [LevelStatus.INPROGRESS, LevelStatus.FAILED]:
			raise LogSyntaxError("Interaction on unloaded/finished level: " + self.stats['status'].name)

		# bump end time on interaction
		self.stats['lastInteraction'] = event['Time']
		if self.stats['lastInteraction'] < self.stats['startTime']:
			raise LogSyntaxError("Level start time " + str(self.stats['startTime']) + " should be before last interaction " + str(self.stats['lastInteraction']) + "!")


	def onInteractionDrawing(self, event: EVENT_T):
		"""Called when the player is using the drawing tools. 
		
		This method will call `self.onInteraction(event)`.
		"""
		assert isinstance(self.stats['drawn'], int)

		if not self.isTask():
			pass#TODO FIXME REMOVE raise LogSyntaxError("Draw tools used in a level without a task.")

		# NOTE Skipping the plausibility check, since a player might be able to release 
		# the drawing after the confirm click
		self.onInteraction(event, check=False)
		self.stats['drawn'] += 1


	def onPageReload(self):
		"""Called when the player reloads the page. The current level will then be resend by the server."""
		assert isinstance(self.stats['status'], LevelStatus)

		self.reloadFlag = True
		if ENABLE_SPECIAL_CASES:					
			if self.stats['status'] != LevelStatus.SOLVED:
				self.stats['status'] = LevelStatus.RELOADED

			self.oldAttempts.append(self.stats)
			self.stats = StatsLevel.createStatsLevel()


	def onFail(self, event: EVENT_T):
		assert isinstance(self.stats['status'], LevelStatus)

		if self.stats['status'] not in [LevelStatus.INPROGRESS, LevelStatus.SOLVED]:
			raise LogSyntaxError("Failed quali but level is in wrong state: " + self.stats['status'].name)

		self.stats['endTime'] = event['Time']
		self.stats['status'] = LevelStatus.FAILED

		if self.stats['endTime'] < self.stats['startTime']:
			raise LogSyntaxError("Level start time " + str(self.stats['startTime']) + " should be before end time " + str(self.stats['endTime']) + "!")


	def getDuration(self, endTime: str = 'endTime') -> Optional[float]:
		"""Get the duration the player spend in this phase, or -1 if the phase was never started. 
		
		Use endTime='firstTryTime' if you need the time before the first confirm click
		"""
		if self.stats['status'] in [LevelStatus.NOTREACHED, LevelStatus.NOTSTARTED]:
			return None

		# If the player stopped playing, use the time provided by post
		if endTime == 'endTime' and self.stats[endTime] == TIME_NONE:
			endTime = 'unloadTime'

		assert isinstance(self.stats['startTime'], datetime)
		assert isinstance(self.stats[endTime], datetime)
		return calculateDuration(self.stats['startTime'], self.stats[endTime]) # type: ignore[reportGeneralTypeIssues]


	def getIES(self, firstTry: bool = False) -> Optional[float]:
		"""Calculate the inverse efficiency score for this level. 

		If firstTry is true, calculate the IES with the time until the player first clicked confirm.
		"""
		assert isinstance(self.stats['status'], LevelStatus), "isinstance(self.stats['status'], LevelStatus)"
		assert isinstance(self.stats['switchClicks'], int), "isinstance(self.stats['switchClicks'], int)"
		assert isinstance(self.stats['minSwitchClicks'], int), "isinstance(self.stats['minSwitchClicks'], int)"
		assert isinstance(self.stats['confirmClicks'], int), "isinstance(self.stats['confirmClicks'], int)"

		duration = self.getDuration('firstTryTime' if firstTry else 'endTime')

		if not self.isSolved() or duration is None:
			return None

		return calculateIES(
			self.stats['switchClicks'], 
			self.stats['minSwitchClicks'], 
			self.stats['confirmClicks'],
			duration
		)


	def getStats(self, firstRun: bool = True) -> LEVEL_ATTRIB_T:
		# If the legacy special cases are disabled, the level inconsistencies on page reload are gone as well
		if not ENABLE_SPECIAL_CASES:
			return self.stats

		if not firstRun or len(self.oldAttempts) <= 0:
			return self.stats

		else:
			return self.oldAttempts[0]


	def getAttribute(self, name: str, t: type, firstRun: bool = False) -> Any: # Wish Generics where properly implemented in Python
		# If the legacy special cases are disabled, the level inconsistencies on page reload are gone as well
		if not ENABLE_SPECIAL_CASES:
			assert isinstance(self.stats[name], t), "Attribute does not have expected type!"
			return self.stats[name]

		if not firstRun or len(self.oldAttempts) <= 0:
			reval = self.stats[name]
		else:
			reval = self.oldAttempts[0][name]

		assert isinstance(reval, t), "Attribute does not have expected type!"
		return reval


	def getStatus(self) -> LevelStatus:
		assert isinstance(self.stats['status'], LevelStatus)
		return self.stats['status']


	def getTimestampSeconds(self, key: str) -> float:
		"""Get timestamp in seconds as a floating point number (1.0 is a second)"""
		if isinstance(self.stats[key], datetime):
			return float(cast(datetime, self.stats[key]).timestamp())
		else:
			assert len(str(int(cast(Any, self.stats[key])))) == 10, "Timestamp is probably not in seconds format!"
			return float(cast(float, self.stats[key]))


	def getTimestampMillis(self, key: str) -> int:
		"""Get timestamp in seconds as an integer"""
		if isinstance(self.stats[key], datetime):
			return int(cast(datetime, self.stats[key]).timestamp()*1000)
		else:
			assert len(str(self.stats[key])) == 13, "Timestamp is probably not in milliseconds format!"
			return int(cast(int, self.stats[key]))


	def getInt(self, key: str) -> int:
		assert isinstance(self.stats[key], int)
		return cast(int, self.stats[key])


	def isSolved(self) -> bool:
		assert isinstance(self.stats['status'], LevelStatus)
		return self.stats['status'] == LevelStatus.SOLVED


	@staticmethod
	def createStatsLevel() -> LEVEL_ATTRIB_T:
		return {
			'switchClicks': 0,
			'confirmClicks': 0,
			'minSwitchClicks': -1,
			'startTime': TIME_NONE,
			'firstTryTime': TIME_NONE,
			'lastInteraction': TIME_NONE,
			'unloadTime': TIME_NONE,
			'endTime': TIME_NONE,
			'feedback': False, # NOTE Becomes True not after the confirm click (like level status), but after the level solved dialogue is shown
			'skipped': False,
			'drawn': 0,
			'status': LevelStatus.NOTSTARTED
		}

FILE_TYPES_WITH_SWITCHES = ['level', 'tutorial']
