import argparse
from datetime import datetime, timedelta
import importlib
from itertools import chain
from operator import itemgetter
import os
import logging
import traceback
from typing import Any, Dict, List, Optional, Tuple

from flask import json
import app.config as gameConfig
from app.statistics.activeLogfile import LogfileInfo
from app.statistics.csvFile import CSVFile
from app.statistics.screenshots import checkScreenshots, countScreenshotsInLog, countScreenshotsOnDisk
from app.statistics.specialCases import specialCase3_5_8_10, specialCase7
from app.statistics.statsLevel import FILE_TYPES_WITH_SWITCHES
from app.statistics.statsParticipant import StatsParticipant
from app.statistics.staticConfig import MAX_LOGFILE_SIZE, LevelStatus
from app.statistics.statisticUtils import LogFiltered, LogSyntaxError, gatherPseudonym, gatherVersion, parseLogfile, removeprefix, stripLevelName
from app.statistics.statsPhase import StatsPhase
from app.utilsGame import EventType, LogKeys, getShortPseudo

# --- New Options: Take the logfiles from database instead of from command line ---
READ_FROM_DB = True


# --- Default values ---
LOGFILE_LOCATION = "statistics"

PRINT_RECONNECTS_SUMMARY = True # Print " --- Reconnects ---" at the end
PRINT_HIGH_TIMESYNC_SUMMARY = True # Print " --- High Time drifts ---" at the end

PRINT_HIGH_TIMESYNC_DETAILS = False # Print every critical time drift when it is found
PRINT_HIGH_TIMESYNC_SUMMARY_MIN_COUNT = 0 # Allow a certain number of big drifts if they cancel out

# --- Command line config options ---
location_logs = "LogFiles"
location_pics = "canvasPics"
location_gameConfig = "instance/conf/gameConfig.json"
skip_pic_inspection = False
timeline_events = 'client' # client or server
timesync_threshold = 40.0 # s

# --- Stats about the logs ---
statsVersion: Dict[str, int] = {}

logStats: Dict[str, List[str]] = {
	"outputLogs": [], 		# All Logs that ended up in the csv (combination of completeLogs and incompleteLogs)
	"completeLogs": [], 	# Logs where the participant solved all levels
	"incompleteLogs": [], 	# Logs where the participant quit early
	"filteredLogs": [], 	# Logs that don't match the filter criteria
	"errorLogs": [], 		# Logs that threw a LogSyntaxError / the validation failed
	"exceptionLogs": [], 	# Logs that threw an unexpected exception. Further investigation needed
	"emptyLogs": [], 		# Game was not even started (Crawler, etc.)
	"restitched": [], 		# These were dropped, because they where merged/stitched into new logs
}

userStats: Dict[str, int] = {
	"partsThrownBack": 0 # Number of times all participants have been thrown back
}

reconnects: Dict[str, list[str]] = {}

# Logs that have a high sum of time deviations
criticalTimeDriftLogs: list[StatsParticipant] = []

# --- Logs that get special attention if they threw an error ---
vipLogs = []
vipLogErrors: Dict[str, Tuple[Exception, int]] = {}


def readSingleLog(
		parsedFile: List[Dict[str, Any]],
		pseudonym: str, group: str, folderPath: str,
		allowDebug: bool
	) -> StatsParticipant:

	# Gather the logfile version
	logfileVersion = gatherVersion(parsedFile)

	# Count how many logfiles of each version exist
	if logfileVersion in statsVersion:
		statsVersion[logfileVersion] += 1
	else:
		statsVersion[logfileVersion] = 1

	# Gather the logfile version and create a Logfile Info Object
	LogfileInfo(pseudonym, parsedFile, logfileVersion)
	logging.debug(pseudonym + " (v" + logfileVersion + "): ")

	# check if the logfile contains at least four events, otherwise it is considered empty and is silently dropped.
	if len(parsedFile) < 5:
		logStats["emptyLogs"].append(pseudonym)
		raise LogFiltered("The log is too small (" + str(len(parsedFile)) +" events).")

	# Throw out all logs that don't match the group filter
	tmpGroup = removeprefix(group, 'debug') if group != 'debug' else group

	if len(groupFilter) > 0 and (tmpGroup if allowDebug else group) not in groupFilter:
		raise LogFiltered(group + " is not in " + str(groupFilter) + ".")
	
	# Do the actual logfile parsing, extract the player statistics from the list of events
	participant = generateStatistics(parsedFile, pseudonym, logfileVersion)
	logStats["outputLogs"].append(pseudonym)

	# Append reconnects
	reconnects[participant.pseudonym] = []
	for r in participant.reconnects:
		reconnects[participant.pseudonym].append(r)

	# Additionally check the screenshots
	if not skip_pic_inspection:
		allPicsInLog = countScreenshotsInLog(participant)

		# First look on disk to find all screenshots written, then compare them with the logs
		if sum(allPicsInLog.values()) > 0:
			allPicsOnDisk = countScreenshotsOnDisk(folderPath, pseudonym, location_pics)
			checkScreenshots(allPicsOnDisk, allPicsInLog, participant)

	return participant


def readLogfiles(folderPath: str, outputPath: str = "statistics.csv", groupFilter: List[str] = [], \
		allowDebug: bool = False) -> List[StatsParticipant]:

	participants: List[StatsParticipant] = []

	# Print absolute folderPath for debugging purposes
	try:
		logging.info("Reading statistics from \"" + os.path.abspath(folderPath) + "\".")
	except Exception as e:
		logging.exception(e)

	try:
		# list all log files inside the folder
		logFiles = [fp for fp in os.listdir(folderPath)]
		logFiles.sort()

		for filePath in logFiles:
			# skip over files that don't match the logFile naming convention
			if not (filePath.startswith("logFile_") and filePath.endswith(".txt")):
				logging.info("Skipping \"" + filePath + "\".")
				continue

			logfileVersion = None
			pseudonym = filePath.removeprefix("logFile_").removesuffix(".txt")

			try:
				# Sanity check file size
				if os.path.getsize(os.path.join(folderPath, filePath)) > MAX_LOGFILE_SIZE:
					logging.error("Error: The file \"" + filePath + "\" is way too big!")
					logStats["exceptionLogs"].append(filePath)
					continue
				
				# Read a single file into a python array containing dict entries
				logging.debug('')
				with open(os.path.join(folderPath, filePath), mode="r", encoding="utf-8") as f:
					parsedFile = parseLogfile(f)

				pseudonym = gatherPseudonym(parsedFile, filePath)
				group = gatherGroup(parsedFile, pseudonym, '??')
				logfileVersion = gatherVersion(parsedFile)

				# Skip over renamed logfiles
				if filePath != "logFile_" + pseudonym + ".txt":
					logging.info("Skipping \"" + filePath + "\"!")
					continue

				participant = readSingleLog(
					parsedFile=parsedFile,
					pseudonym=pseudonym,
					group=group,
					folderPath=folderPath,
					allowDebug=allowDebug
				)

				participants.append(participant)

			# Handle all Logs that don't match the criteria for the current analysis
			except LogFiltered as e:
				logStats["filteredLogs"].append(pseudonym)
				if pseudonym in vipLogs:
					vipLogErrors[pseudonym] = (e, LogfileInfo.getActive().getOriginLine())

			# Handle Errors that occur due to invalid logfiles
			except LogSyntaxError as e:
				logging.error(
					"Validation of " + getShortPseudo(removeprefix(filePath, 'logFile_')) + 
					" failed (v" + str(logfileVersion) + ", ln. " + str(e.originLine).rjust(4, ' ') + "): " + str(e)
				)
				logStats["errorLogs"].append(pseudonym)
				if pseudonym in vipLogs:
					vipLogErrors[pseudonym] = (e, LogfileInfo.getActive().getOriginLine())

			# Handle missing files (especially screenshots folder)
			except FileNotFoundError as e:
				logging.error('Error, FileNotFound: "' + e.filename + '"!')

			# Handle Errors that occur if the encoding of the logfile is wrong
			except UnicodeDecodeError as e:
				logging.error("The file \"" + filePath + "\" is not in UTF-8 format, probably Windows-1252")
				logStats["filteredLogs"].append(pseudonym)
				if pseudonym in vipLogs:
					vipLogErrors[pseudonym] = (e, LogfileInfo.getActive().getOriginLine())

			# Handle all other errors, so that the parsing can go on. Errors handled by this catch are severe and need further investigation
			except Exception as e:
				# this is not our exceptions, something went wrong, print the whole stack
				logging.error("An error occurred while parsing \"" + filePath + "\":")
				traceback.print_exc()
				logStats["exceptionLogs"].append(pseudonym)
				if pseudonym in vipLogs:
					vipLogErrors[pseudonym] = (e, LogfileInfo.getActive().getOriginLine())

	except Exception:
		traceback.print_exc()

	return participants


def readLogfilesFromDB(folderPath: str, outputPath: str = "statistics.csv",
		groupFilter: List[str] = [], allowDebug: bool = False) -> list[StatsParticipant]:
	
	from app.statistics.logConverter import getAllParticipantsFromDB, getLogEntriesFromDB_asLegacy

	participants: list[StatsParticipant] = []

	for pseudonym in getAllParticipantsFromDB():
		logfileVersion = '?.?.?'

		try:
			rawFile = ''.join(getLogEntriesFromDB_asLegacy(pseudonym, writeToFile=False))
			parsedFile = parseLogfile(rawFile.splitlines())

			group = gatherGroup(parsedFile, pseudonym, '??')
			logfileVersion = gatherVersion(parsedFile)

			participant = readSingleLog(
				parsedFile=parsedFile,
				pseudonym=pseudonym,
				group=group,
				folderPath=folderPath,
				allowDebug=allowDebug
			)

			participants.append(participant)

		# Handle all Logs that don't match the criteria for the current analysis
		except LogFiltered as e:
			logStats["filteredLogs"].append(pseudonym)
			if pseudonym in vipLogs:
				vipLogErrors[pseudonym] = (e, LogfileInfo.getActive().getOriginLine())

		# Handle Errors that occur due to invalid logfiles
		except LogSyntaxError as e:
			logging.error(
				"Validation of " + getShortPseudo(pseudonym) + 
				" failed (v" + str(logfileVersion) + ", ln. " + str(e.originLine).rjust(4, ' ') + "): " + str(e)
			)
			logStats["errorLogs"].append(pseudonym)
			if pseudonym in vipLogs:
				vipLogErrors[pseudonym] = (e, LogfileInfo.getActive().getOriginLine())

		# Handle all other errors, so that the parsing can go on. Errors handled by this catch are severe and need further investigation
		except Exception as e:
			# this is not our exceptions, something went wrong, print the whole stack
			logging.error("An error occurred while parsing \"" + pseudonym + "\":")
			traceback.print_exc()
			logStats["exceptionLogs"].append(pseudonym)
			if pseudonym in vipLogs:
				vipLogErrors[pseudonym] = (e, LogfileInfo.getActive().getOriginLine())

	return participants


def generateStatistics(log: List[Dict[str, Any]], pseudonym: str, version: str, sortByTime: bool = True) -> StatsParticipant:
	participant = StatsParticipant(pseudonym)
	lastEvent = None
	outOfOrder = -1
	gameStartedIndex = -1
	timeDelta: Optional[timedelta] = None # positive number means client time is ahead

	# Set some player log stats
	participant.numEvents = len(log)
	#participant.startTime = log[0][LogKeys.TIME] # NOTE Disabled as the first event might not hold the correct time

	# Decide if we need to sort the log
	for i, event in enumerate(log):
		# Search for the beginning of the player interaction. (In old logfiles, the timestamps of Group Assignment etc. 
		# might be scuffed, therefore only start sorting after the first Scene (PreloadScene) is loaded)
		if event[LogKeys.EVENT] == EventType.PhaseRequested and gameStartedIndex < 0:
			gameStartedIndex = i

		# Do not use reconnects for the final post call
		if event[LogKeys.EVENT] != EventType.BackOnline:
			lastEvent = event

		# Check that the time always increments!
		if lastEvent is not None and lastEvent[LogKeys.TIME].timestamp() > event[LogKeys.TIME].timestamp():
			outOfOrder += 1

		# Catch Time Sync events
		if event[LogKeys.EVENT] == EventType.TimeSync:
			newTimeDelta: timedelta = event[LogKeys.TIME] - event[LogKeys.TIME_SERVER]

			if timeDelta is None:
				timeDelta = newTimeDelta
			
			else:
				# If the `timeDrift` is bigger than `timesync_threshold` use the `newTimeDelta`
				timeDrift: timedelta = timeDelta - newTimeDelta
				timeDriftStr = (' ' if timeDrift.total_seconds() > 0 else '-') + str(abs(timeDrift.total_seconds()))
				if abs(timeDrift.total_seconds()) > timesync_threshold:
					participant.criticalTimeDrifts.append(timeDrift.total_seconds())
					timeDelta = newTimeDelta

					if PRINT_HIGH_TIMESYNC_DETAILS:
						logging.warning(f"{getShortPseudo(participant.pseudonym)}: " + \
					 			f"Ping Spike/tampered client time: Drifted {timeDriftStr}s in ln {i+1}!"
						)

		# Calculate server time if not logged
		if LogKeys.TIME_SERVER not in event and timeDelta is not None:
			event[LogKeys.TIME_SERVER] = event[LogKeys.TIME] - timeDelta

	# Logfile is basically empty or invalid
	if gameStartedIndex < 0:
		raise LogSyntaxError("Unable to sort, no scene was loaded within the first 20 events!")

	# Append all Participants that have suspicious time drift to a list for later evaluation
	if len(participant.criticalTimeDrifts) > 0:
		criticalTimeDriftLogs.append(participant)

	# Sort the log file, if out of order
	if outOfOrder > 0:
		if sortByTime:
			# Use Pythons builtin sort which should be stable 
			# https://docs.python.org/3/howto/sorting.html#sort-stability-and-complex-sorts
			log[gameStartedIndex:] = sorted(log[gameStartedIndex:], key=itemgetter('Time'))
			logging.warning("Sorted "+ str(outOfOrder) + " events in " + getShortPseudo(pseudonym) + "!")

		else:
			# Sorting is disabled, only print warning
			logging.warning("Events for " + getShortPseudo(pseudonym) + " are not in chronological order (" + str(outOfOrder) + ")")


	# Feed the events to the participant/outline
	# NOTE Using the good ol while loop, to avoid undefined behavior cause we need to insert while iterating
	i = -1
	while i < len(log) - 1:
		i += 1
		event = log[i]

		assert isinstance(event[LogKeys.EVENT], str)
		assert isinstance(event[LogKeys.TIME], datetime)
		LogfileInfo.getActive().activeEvent = event
		LogfileInfo.getActive().eventIndex = i

		# Do not use reconnects for the final post call
		if event[LogKeys.EVENT] != EventType.BackOnline:
			lastEvent = event

		# Make sure no Filename ends with .txt
		if LogKeys.FILENAME in event:
			event[LogKeys.FILENAME] = stripLevelName(event[LogKeys.FILENAME])

		# NOTE: You can mark some events to be skipped, e.g. because they have been handled earlier
		if int(event[LogKeys.ORIGIN_LINE]) < -100:
			continue
		
		# Special case 03, 05, 08 and 10
		specialCase3_5_8_10(participant, log, event, i, version)

		# Handle the current event
		try:
			participant.handleEvent(event)
		except LogSyntaxError as e:
			# Append reconnects
			reconnects[participant.pseudonym] = []
			for r in participant.reconnects:
				reconnects[participant.pseudonym].append(r)

			# Add the current log line and rethrow the error
			if LogKeys.ORIGIN_LINE in event:
				e.originLine = event[LogKeys.ORIGIN_LINE]
			raise e
			

	# Call post for the last entry in the log, to terminate the active scene
	if lastEvent is not None:
		participant.post(lastEvent)
	else:
		logging.warning("Could not call post, the log file is empty!")

	# NOTE Make sure this is called last, so that no Logs are appended that threw an error
	return participant


def stitchLogfiles(participants: list[StatsParticipant], stitchOrder: Dict[str, List[List[str]]]):
	# Flatten the 2D stitch instruction array to extract all source pseudonyms
	sourcePseudonyms = {so[0] for so in chain.from_iterable(stitchOrder.values())}
	sourceData: Dict[str, StatsParticipant] = {}

	firstEntry = True

	# Pop all source participants from the list and add them to sourceData
	i = 0
	while i < len(participants):
		psdnm = participants[i].pseudonym
		if psdnm in sourcePseudonyms:
			sourceData[psdnm] = participants[i]
			try: logStats['outputLogs'].remove(psdnm)
			except Exception: pass
			logStats['restitched'].append(psdnm)
			participants.pop(i)
		else:
			i += 1

	# Create new Participant from stitched sources
	for destPseudo, sources in stitchOrder.items():
		try:
			newParticipant: Optional[StatsParticipant] = None
			levelPhaseMap: Dict[str, StatsPhase] = {}
			loadedLevels: list[str] = []
			levelCounter = 0

			# Iterate over each source for the new participant
			for source in sources:
				sourcePseudo = source[0]
				sourceLevels = source[1:]
				try: 
					sourceParticipant = sourceData[sourcePseudo]
				except KeyError as e:
					lfn = sourcePseudo #"logFile_" + sourcePseudo + ".txt"
					msg = " failed validation" if lfn in logStats["errorLogs"] else " pseudonym does not exist!"
					raise KeyError(sourcePseudo + msg)

				# Create participant if not existent, otherwise check that the groups match
				if newParticipant is None:
					newParticipant = StatsParticipant(destPseudo)
					newParticipant.onGroupAssignment({'Group': sourceParticipant.groups[0]})
					levelPhaseMap = newParticipant.getLevelPhaseMapping()
				else:
					assert newParticipant.groups[0] in sourceParticipant.groups

				# For every level get the source and dest and then copy over the stats on a per level basis
				for level in sourceLevels:
					assert level not in loadedLevels, 'Duplicate level entry, "' + level + '" has already been merged!'
					destPhase = levelPhaseMap[level]
					sourceStats = sourceParticipant.getPhaseByName(destPhase.name, firstEntry=firstEntry).getLevelByName(level).stats
					destLevel = destPhase.getLevelByName(level)
					destLevel.stats = sourceStats
					destLevel.position = levelCounter
					levelCounter += 1
					loadedLevels.append(level)

				# Build statistics of how many levels have been merged
				NEVER_STARTED_STATES = [LevelStatus.NOTREACHED]
				participantData = chain.from_iterable([phase.levels for phase in sourceParticipant.statsPhase])
				allDataSets = [
					d for d in participantData 
					if d.type in FILE_TYPES_WITH_SWITCHES 
					and d.getStatus() not in NEVER_STARTED_STATES
				]
				print(getShortPseudo(sourcePseudo) + ": " + str([l.name for l in allDataSets]) + ", " + str(sourceLevels))

			assert newParticipant is not None
			logStats["outputLogs"].append(destPseudo)
			participants.append(newParticipant)
			logging.info('Stitched "' + destPseudo + '" from ' + str(len(sources)) + " logs.")
		except Exception as e:
			logging.error("Could not stitch " + destPseudo + ': "' + str(e) + '"')


def gatherGroup(log: List[Dict[str, Any]], pseudonym: str, version: str) -> str:
	"""Get the group from the log"""
	# TODO Replace with version from statisticUtils.py when Special case is removed
	assert len(log) > 0
	group = None

	for i in range(0, min(9, len(log))):
		if log[i]['Event'] == "Group Assignment":
			group = str(log[i]['Group'])
			break

	# Special case 07
	specialCase7(log, version=version, pseudonym=pseudonym, group=group)

	if group is None:
		raise LogSyntaxError("The group assignment is missing from the logs (v" + version + ")!")

	return group


def main():
	global location_logs, location_pics, location_gameConfig, skip_pic_inspection
	global timesync_threshold, header, groupFilter, attributes, vipLogs, timeline_events

	parser = argparse.ArgumentParser(description="A script to aggregate the logfiles from the ReverSim game into a csv file.")
	parser.add_argument("csvGenerator", help="The script to be used to generate the csv file. \"app/statistics/csvGenerators/\"")
	parser.add_argument("-l", "--log", metavar='LEVEL', help="Specify the log level, must be one of DEBUG, INFO, WARNING, ERROR or CRITICAL", default="INFO")
	parser.add_argument("-d", "--allowDebug", help="Allow debug groups to end up in the output", action="store_true")
	parser.add_argument("-p", "--logPath", help="The path to search for the logfiles", default=LOGFILE_LOCATION)
	parser.add_argument("-o", "--output", help="The filename of the output statistic csv file", default='statistics.csv')
	parser.add_argument("-s", "--skipScreenshots", help="Skip the screenshot validation", action="store_true")
	parser.add_argument("--folderLogs", help="The location of the logfiles. The script will search for the folder LogFiles in this location", default=location_logs)
	parser.add_argument("--folderPics", help="The location of the screenshots", default=location_pics)
	parser.add_argument("--config", help="Additional instructions for the log parser (merging, vip logs etc.)", default=None)
	parser.add_argument("-g", "--gameConfig", help="The gameConfig.json that shall be used", default=location_gameConfig)
	#parser.add_argument("-t", "--timeline", help="Decide if the parsed events should be converted to server time", choices=['client', 'server'], default='client')
	parser.add_argument("--syncThreshold", metavar="SECONDS", type=float, help="Raise a warning, if the client and "\
			"server time drift apart more than the specified threshold in seconds. Set to zero to disable. "\
			"Keep in mind that TimeSync events are only fired, if the client and server time deviate at least by "\
			"config.py@TIME_DRIFT_THRESHOLD (0.2)", default=40 #s
	)
	
	args = parser.parse_args()
	try:
		logLevel = getattr(logging, args.log.upper())
	except Exception as e:
		print("Invalid log level: " + str(e))
		exit(-1)

	# Set logging format
	logging.basicConfig(
		format='[%(levelname)s] %(message)s',
		level=logLevel,
	)

	# Args
	location_logs = args.folderLogs
	location_pics = args.folderPics
	skip_pic_inspection = args.skipScreenshots
	#timeline_events = args.timeline TODO
	timesync_threshold = args.syncThreshold
	location_gameConfig = args.gameConfig

	# Dynamically load the csv generator
	try:
		csvGenerator = importlib.import_module('app.statistics.csvGenerator.' + args.csvGenerator)
		header = csvGenerator.header
		groupFilter = csvGenerator.groupFilter
		attributes = csvGenerator.attributes
		levelHeaderFormat = csvGenerator.LEVEL_HEADER_FORMAT

	except (ModuleNotFoundError, AttributeError) as e:
		logging.critical(str(e))
		exit(-42)

	# Load the game config
	os.environ.setdefault("REVERSIM_CONFIG", location_gameConfig)
	gameConfig.loadGameConfig(location_gameConfig)

	# Load the log parser config
	logParserConfig: Dict[str, Any] = {}
	if args.config is not None:
		try:
			with open(args.config, "r", encoding="utf-8") as f:
				logParserConfig = json.load(f)
		except Exception as e:
			logging.exception(e)

	# Load VIP logs if applicable
	VIP_LOG_KEY = 'vip'
	if VIP_LOG_KEY in logParserConfig:
		assert isinstance(logParserConfig[VIP_LOG_KEY], list)
		vipLogs = sorted(logParserConfig[VIP_LOG_KEY])

	# Prepare the csv 
	fileName = 'statistics_' + args.csvGenerator +'.csv'
	outputFile = CSVFile(fileName, csvGenerator.header, csvGenerator.attributes, levelHeaderFormat)
	outputFile.checkOutputFile()

	# Parse all logs using the new Database log format if enabled
	if READ_FROM_DB:
		participants = readLogfilesFromDB(
			args.logPath + '/' + location_logs, 
			args.output, 
			groupFilter=csvGenerator.groupFilter, 
			allowDebug=args.allowDebug
		)

	# Else read in old plaintext logfiles
	else:
		participants = readLogfiles(
			args.logPath + '/' + location_logs, 
			args.output, 
			groupFilter=csvGenerator.groupFilter, 
			allowDebug=args.allowDebug
		)
	

	# Print all reconnects
	if PRINT_RECONNECTS_SUMMARY:
		print("")
		print(" --- Reconnects ---")

		for psdnm, rcons in reconnects.items():
			for r in rcons:
				if r == "Start": continue
				logging.info(f'{getShortPseudo(psdnm)}: {r}')

		print("")

	# Report high client/server time drifts
	if PRINT_HIGH_TIMESYNC_SUMMARY and len(criticalTimeDriftLogs) > 0:
		print("")
		print(" --- High Time drifts ---")
		for p in criticalTimeDriftLogs:
			sumDrift = round(sum(p.criticalTimeDrifts), 2)
			absSumDrift = round(sum(abs(x) for x in p.criticalTimeDrifts), 2)
			numDrift = len(p.criticalTimeDrifts)

			# If there are too many time occasions where the client server time drift spikes, or when the sum of the 
			# time sync events is bigger than the time sync threshold, report them.
			if numDrift <= PRINT_HIGH_TIMESYNC_SUMMARY_MIN_COUNT and abs(sumDrift) < timesync_threshold:
				continue

			print(f'{getShortPseudo(p.pseudonym)}: Count={numDrift}, Sum={sumDrift}, AbsSum={absSumDrift}')
		print("")


	# Intermediate step: Stitch logfiles in case of a game crash
	MERGE_KEY = 'stitch' # 'merge'
	if MERGE_KEY in logParserConfig and len(logParserConfig[MERGE_KEY]) > 0:
		print("")
		print(" --- Log stitcher ---")
		stitchLogfiles(participants, logParserConfig[MERGE_KEY])
		print("")


	# Append each participant to the output csv
	logging.info("Generating CSV")
	for p in participants:
		try:
			outputFile.appendParticipant(p)
		except Exception as e:
			traceback.print_exc()

	# Sanity Check: Make sure the length of the output logs match the expectations	
	assert len(logStats["outputLogs"]) == len(outputFile.rows), "Expected Num of Logs: " \
			+ str(len(logStats["outputLogs"])) + ", Rows in the CSV: " + str(len(outputFile.rows))

	logging.info(str(len(logStats["outputLogs"])) + " have been added to the statistics.")

	outputFile.write()

	# VIP Logfiles: These are expected to be inside the CSV, if they are not display the reason
	if len(vipLogErrors) > 0:
		print("")
		print(" --- VIP Logs with errors ---")
		logs = [
			getShortPseudo(ps) + ":" + (str(vipLogErrors[ps][1]).ljust(4, ' ') + " " + str(vipLogErrors[ps][0])) \
			if ps in vipLogErrors else getShortPseudo(ps) + "...:xxxx Unknown???" \
			for ps in vipLogs if 'logFile_' + ps + ".txt" not in logStats['outputLogs']
		]
		for l in logs:
			print(l)


	# Print a newline at the end
	print()


# program entry point
# NOTE: Minimum Python Version: 3.10
if __name__ == "__main__":
	main()
