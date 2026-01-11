from io import TextIOWrapper
from typing import Optional

from app.gameConfig import MAX_ERROR_LOGS_PER_PLAYER, PSEUDONYM_LENGTH
from app.prometheusMetrics import ServerMetrics
from app.storage.participantsDict import exists
from app.utilsGame import now

crashReportFile: Optional[TextIOWrapper] = None

crashCounts: dict[str, int] = {}
groupBlacklist: list[str]

def openCrashReporterFile(filePath: str, p_groupBlacklist: list[str], errorLevel: int):
	"""Open the error log file in text append mode and write a message"""
	global crashReportFile
	global groupBlacklist

	groupBlacklist = p_groupBlacklist

	try:
		# NOTE: Not using a with statement, since the logfile shall stay open
		crashReportFile = open(filePath, 'ta', encoding='UTF-8', newline='\n')
		crashReportFile.write(f'\n[{now()}] Initializing client crash reporter (Level: {errorLevel})')
		crashReportFile.write('\n')
		crashReportFile.flush()

	except Exception as e:
		print('Unable to open the crash report file "' + filePath + '": ' + str(e))


def writeCrashReport(pseudonym: str, group: str, timestamp: int, message: str, stackTrace: str) -> bool:
	"""Write a crash report to the error log file. Returns true if successful, false otherwise."""
	# Check if crash reports are enabled globally and that this group is no blacklisted
	if not isCrashReporterEnabled(group):
		return False
	else:
		assert crashReportFile is not None

	# make sure pseudonym is correct length and contains a hex number
	pseudonym = pseudonym[:PSEUDONYM_LENGTH]
	if not pseudonym.isalnum():
		return False

	# reject if pseudonym is not in player database
	if not exists(pseudonym):
		return False	

	# reject, if the player threw too many errors
	if pseudonym not in crashCounts:
		crashCounts[pseudonym] = 0
	elif MAX_ERROR_LOGS_PER_PLAYER > 0 and crashCounts[pseudonym] > MAX_ERROR_LOGS_PER_PLAYER:
		return False

	san_timestamp = int(timestamp)
	san_message = '%20'.join(str(message.strip()).splitlines(keepends=False))
	san_trace = stackTrace.splitlines(keepends=False)

	# Update the Prometheus metrics
	ServerMetrics.incrementCrashMetrics()

	# Increase the logged errors counter and return success
	crashCounts[pseudonym] += 1

	try:
		# Write to crash reporter file
		crashReportFile.write(f'\n[{san_timestamp}] ui="{pseudonym}":\n')
		crashReportFile.write(san_message)

		for line in san_trace:
			crashReportFile.write('\n\t' + line.strip())

		crashReportFile.write('\n')
		crashReportFile.flush()
		return True

	except Exception as e:
		print('Unable to write crash report: ' + str(e))
		
	return False


def isCrashReporterEnabled(groupName: str) -> bool:
	"""True, if client errors shall be written to a log file, false otherwise."""
	# If the file is not open, client error logging is disabled (or the error log couldn't be opened)
	if crashReportFile is None:
		return False
	
	# Reject all groups, where error logging is disabled (for privacy reasons etc.)
	if groupName in groupBlacklist:
		return False
	
	return True
