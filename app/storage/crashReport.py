from io import TextIOWrapper
from typing import Optional

from prometheus_client import Gauge

from app.config import MAX_ERROR_LOGS_PER_PLAYER, PSEUDONYM_LENGTH
from app.storage.participantsDict import exists
from app.utilsGame import now

crashMetric: Optional[Gauge] = None
crashReportFile: Optional[TextIOWrapper] = None

crashCounts: dict[int, int] = {}
groupBlacklist: list[str]

def openCrashReporterFile(filePath: str, p_groupBlacklist: list[str], p_crashMetrics: Optional[Gauge], errorLevel: int):
	"""Open the error log file in text append mode and write a message"""
	global crashReportFile
	global groupBlacklist
	global crashMetric

	groupBlacklist = p_groupBlacklist
	crashMetric = p_crashMetrics

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

	ui_num = int(pseudonym[:PSEUDONYM_LENGTH], base=16)
	san_pseudonym = hex(ui_num)[2:] # make sure string is a hex number, remove 0x prefix
	san_timestamp = str(timestamp)
	san_message = '%20'.join(str(message.strip()).splitlines(keepends=False))
	san_trace = stackTrace.splitlines(keepends=False)

	# reject if pseudonym is unknown
	if not exists(san_pseudonym):
		return False
	
	# reject, if the player threw too many errors
	if ui_num not in crashCounts:
		crashCounts[ui_num] = 0
	elif MAX_ERROR_LOGS_PER_PLAYER > 0 and crashCounts[ui_num] > MAX_ERROR_LOGS_PER_PLAYER:
		return False

	# Update the Prometheus metrics
	updateCrashMetrics()

	# Increase the logged errors counter and return success
	crashCounts[int(pseudonym[:PSEUDONYM_LENGTH], base=16)] += 1

	try:
		crashReportFile.write('\n[' + san_timestamp + '] ui=' + san_pseudonym + ':\n')
		crashReportFile.write(san_message)

		for l in san_trace:
			crashReportFile.write('\n\t' + l.strip())

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


def updateCrashMetrics():
	"""Update the Prometheus metric for client errors/crashes"""
	try: 
		if crashMetric is not None:
			crashMetric.inc() # Increment the `reversim_client_errors` metric
	except Exception:
		pass
