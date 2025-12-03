from datetime import datetime, timezone
import math

from typing import Any, Dict, Iterable, List, Optional

from app.utilsGame import LogKeys


# Unresolved Bug in Python for Dates with no Timezone set which are close to 01.01.1970
# Workaround: Make sure the Timezone is set
# https://github.com/python/cpython/issues/81708
# https://stackoverflow.com/questions/56931738/python-crash-on-windows-with-a-datetime-close-to-the-epoch?noredirect=1#comment100413591_56931738
tz = timezone.utc

TIME_NONE = datetime.fromtimestamp(0, tz).replace(year=1970, tzinfo=tz)

class LogSyntaxError(Exception):
	"""The log file did not pass the validation tests."""
	def __init__(self, message: str, originLine: int = -404):
		super().__init__(message)
		self.originLine = originLine
		pass

class LogFiltered(Exception):
	"""The log was dropped, because some of the filters determined, that this log is irrelevant for this analysis.

	Reasons could be:
		- The participant was in an irrelevant group
		- The group name started with debug
	"""
	pass


class StatisticsError(Exception):
	"""Thrown when something went wrong during the generation of the statistics"""


def calculateIES(numSwitchClicks: int, minSwitchClicks: int, numConfirmClicks: int, timeTaken: float) -> float:
	"""Calculate the inverse efficiency score. 
	
	timeTaken is in seconds
	"""
	assert numSwitchClicks >= 0, "Assertion failed, numSwitchClicks < 0: " + str(numSwitchClicks)
	assert minSwitchClicks >= 0, "Assertion failed, minSwitchClicks < 0: " + str(minSwitchClicks)
	assert numConfirmClicks > 0, "Assertion failed, numConfirmClicks > 1: " + str(numConfirmClicks)
	assert timeTaken > 0, "The time it took to solve the level must be greater than zero: " + str(timeTaken) + "!"
	assert numSwitchClicks >= minSwitchClicks, "NumSwitchClicks must be >= minSwitchClicks: " + str(numSwitchClicks) + "/" + str(minSwitchClicks)

	timeTakenSeconds: float = timeTaken
	w = numSwitchClicks - minSwitchClicks
	d = numConfirmClicks - 1
	pc = (1/(1 + w)) * (1/(1 + d))
	return timeTakenSeconds / pc


def parseLogfile(fileLines: Iterable[str]) -> List[Dict[str, Any]]:
	parsedFile: list[dict[str, Any]] = []
	entry: dict[str, Any] = {}
	#lastTime: Optional[datetime] = None

	# Parse file line by line
	for i, line in enumerate(fileLines):
		# If there is a newline, push log entry to the parsed File
		if line.startswith('\n') or line.startswith('\r') or len(line) == 0:
			if len(entry) > 0:
				if not (LogKeys.EVENT in entry and LogKeys.TIME in entry):
					raise LogSyntaxError("Missing at least one of the necessary keys: \"§Event\" and \"Time\"")
				parsedFile.append(entry)

				entry = {}
			continue
		
		# Else add something to the log entry
		l = line.strip()
		kv = l.split(':', 1)
		if(len(kv) != 2): 
			raise LogSyntaxError("Invalid entry in file, it must be of form \"§key: value\" or \"key: value\". Actually got '" + l + "'")
		
		key = removeprefix(removeprefix(kv[0].rstrip(), 'Â'), '§') # NOTE The Â removal is just a workaround for incorrectly encoded files
		value = kv[1].lstrip()

		# Insert debug info
		if LogKeys.ORIGIN_LINE not in entry:
			entry[LogKeys.ORIGIN_LINE] = i+1

		# Add key and value to log entry
		if key == LogKeys.TIME:
			entry[LogKeys.TIME] = parseTimestamp(value)
			#lastTime = entry[key]
		
		# Read the server time
		elif key == LogKeys.TIME_SERVER:
			parsedTime = parseTimestamp(value)
			entry[LogKeys.TIME_SERVER] = parsedTime

			# Set Time to _serverTime if unpopulated
			if LogKeys.TIME not in entry:
				entry[LogKeys.TIME] = parsedTime

		else:
			assert key not in entry, f'Found duplicate key "{key}" in line {i}'
			entry[key] = value

	# Append the last entry if the log didn't end with a newline
	if 'Time' in entry and 'Event' in entry:
		parsedFile.append(entry)

	return parsedFile


def removeprefix(self: str, prefix: str) -> str:
    if self.startswith(prefix):
        return self[len(prefix):]
    else:
        return self[:]
		

def removesuffix(self: str, suffix: str) -> str:
    # suffix='' should not call self[:-0].
    if suffix and self.endswith(suffix):
        return self[:-len(suffix)]
    else:
        return self[:]


def parseTime(timeString: str) -> Optional[datetime]:
	"""Try to parse a unix timestamp or return None if the number cannot be read as a float"""
	if timeString.isdecimal():
		return parseTimestamp(timeString)
	
	return None


def parseTimestamp(timeString: str) -> datetime:
	"""Parse a unix timestamp from a string into a datetime object"""
	assert not math.isnan(float(timeString)), "the string is not a number (NaN)"
	assert float(timeString) > 0.0, "Could not convert unix time, must be a number greater than zero!"
	return datetime.fromtimestamp(float(timeString)/1000, tz=tz) # time comes in thousands of a second


def calculateDuration(startTime: datetime, endTime: datetime) -> float:
	"""Get the duration the player spend in this phase, or -1 if the phase was never started."""
	assert isinstance(startTime, datetime)
	assert isinstance(endTime, datetime)
	assert startTime.timestamp() > 1, "The start time is not initialized (datetime < 01.01.1970)!"
	assert endTime.timestamp() > 1, "The end time is not initialized (datetime < 01.01.1970)!"
	duration = int(endTime.timestamp() * 1000 - startTime.timestamp() * 1000)
	assert duration >= 0, "The calculated duration is negative: " + str(duration) + "!"
	return duration / 1000


def gatherPseudonym(log: List[Dict[str, Any]], filePath: str) -> str:
	"""Try to get the pseudonym from the log, otherwise get it from the fileName"""
	assert len(log) > 0
	assert 'Event' in log[0]
	assert filePath.startswith('logFile_') and filePath.endswith('.txt')

	if log[0]['Event'] == "Created Logfile" and "Pseudonym" in log[0]:
		return log[0]['Pseudonym']
	else:
		return removesuffix(removeprefix(filePath, "logFile_"), ".txt")


def gatherVersion(log: List[Dict[str, Any]]) -> str:
	"""Gather the logfile version from the log, or assume 0.1.0 if not set"""
	assert len(log) > 0
	assert 'Event' in log[0]

	if log[0]['Event'] == 'Created Logfile':
		return log[0]['Version']
	else:
		return "0.1.0"


def gatherGroup(log: List[Dict[str, Any]], pseudonym: str, version: str) -> str:
	"""Get the group from the log"""
	assert len(log) > 0

	group = None

	for i in range(0, min(9, len(log))):
		if log[i]['Event'] == "Group Assignment":
			group = str(log[i]['Group'])
			break

	if group is None:
		raise LogSyntaxError("The group assignment is missing from the logs (v" + version + ")!")

	return group