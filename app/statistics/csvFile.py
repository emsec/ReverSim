import logging
import os
import traceback
from datetime import datetime
from typing import Any, Callable, Dict, List, Union
from app.statistics.staticConfig import TABLE_DELIMITER, TABLE_FALSE, TABLE_TRUE, LevelStatus, PhaseStatus
from app.statistics.statisticUtils import StatisticsError
from app.statistics.statsLevel import StatsLevel
from app.statistics.statsParticipant import StatsParticipant

from app.statistics.statsPhase import StatsPhase
from app.utilsGame import get_git_revision_hash, getShortPseudo

gLevelHeaderFormat = "None"
globalLevelIndex = -3

LEVEL_ATTRIB_T = Union[str, bool, float, int, None]

legend: Dict[str, List[str]] = {}
tmpHeader: List[str] = []

warningLevelHeaderName = False

class CSVFile:
	def __init__(self, 
				outputPath: str,
				header: List[str],
				attributes: List[Callable[[StatsParticipant], Union[str, bool, float, int, None, List[LEVEL_ATTRIB_T]]]],
				levelHeaderFormat: str = "%(th)s (%(levelIdx)d)"
			) -> None:

		global gLevelHeaderFormat

		assert len(header) == len(attributes), "Header and Attribute length mismatch: " + str(len(header)) + "|" + \
			str(len(attributes)) + "!"

		self.outputPath = outputPath
		self.rows: List[List[Union[LEVEL_ATTRIB_T, List[LEVEL_ATTRIB_T]]]] = []
		self.levelIndex = -1
		
		self.header = header
		self.attribs = attributes
		self.csvHeadline: List[str] = []
		gLevelHeaderFormat = levelHeaderFormat

		self.startTime = datetime.now()


	def appendParticipant(self, participant: StatsParticipant):
		global tmpHeader
		global globalLevelIndex

		globalLevelIndex = 0
		row: List[Union[LEVEL_ATTRIB_T, List[LEVEL_ATTRIB_T]]] = []
		tmpHeader = []

		for i in range(0, len(self.attribs)):
			try:
				tmpHeader.append(self.header[i])
				entry = self.attribs[i](participant)

			except Exception as e:
				entry = ">>> ERROR <<<"
				logging.error("Error while getting attrib (" + getShortPseudo(participant.pseudonym) + "): " + str(e))
				logging.debug(traceback.format_exc())

			row.append(entry)

		self.rows.append(row)

		# Use the header generated for the participant as the header
		# and ensure that the following headers match the first run
		if len(self.csvHeadline) < 1:
			self.csvHeadline = tmpHeader
		else:
			if len(self.csvHeadline) == len(tmpHeader): # Existing header matches the new header
				assert self.csvHeadline == tmpHeader, "The headline of " + participant.pseudonym[:16] + \
					"... does not match the expected header!"

			elif len(self.csvHeadline) > len(tmpHeader): # Existing header is longer than the new header
				# Remove all LEVEL_... headers that did not get replaced
				for h in filter(lambda s: s.startswith("LEVELS_"), tmpHeader):
					tmpHeader.remove(h)

				assert self.csvHeadline[:len(tmpHeader)] == tmpHeader, "The headline of " + participant.pseudonym[:16] + \
					"... does not match the expected header!"
				logging.warning(participant.pseudonym[:16] + "...: " + "The header is shorter by " + \
					str(len(self.csvHeadline)-len(tmpHeader)) + " entries.")

			else: # Existing header is shorter than the new header
				assert self.csvHeadline == tmpHeader[:len(self.csvHeadline)], "The headline of " + participant.pseudonym[:16] + \
					"... does not match the expected header!"
				logging.warning(participant.pseudonym[:16] + "...: " + "The header is longer by " + \
					str(len(tmpHeader)-len(self.csvHeadline)) + " entries.")

		tmpHeader = []


	def addEntry(self, column: int, entry: Any):
		"""Set the value in the specified column to entry for the active participant/in the active row."""
		self.rows[len(self.rows) - 1][column] = self.stringify(entry)


	def stringify(self, entry: Any) -> str:
		"""Generate a csv safe string from multiple datatypes 
		(raises StatisticsError if the type is not supported)
		
		https://owasp.org/www-community/attacks/CSV_Injection
		"""
		# TODO prevent CSV injection
		if entry is None:
			return ''#TABLE_NAN

		elif isinstance(entry, str):
			return entry

		elif isinstance(entry, bool):
			return TABLE_TRUE if entry else TABLE_FALSE

		elif isinstance(entry, float):
			return str(entry)

		elif isinstance(entry, int):
			return str(entry)

		elif isinstance(entry, PhaseStatus) or isinstance(entry, LevelStatus):
			return str(entry.name)

		else:
			raise StatisticsError("Can not safely stringify entry!")
	

	def checkOutputFile(self) -> bool:
		# open/create .csv file, ask the user if the file already exists
		outputPath = "statistics.csv"
		if os.path.exists(outputPath):
			uinput = input("The file already exists, overwrite? [y/N]: ").lower()
			if uinput != "y" and uinput != "yes":
				return True
		return False


	def write(self):
		flatRows: List[List[str]] = []

		if len(self.rows) > 0:
			assert len(legend) > 0, "The legend is empty, even though there are logs loaded."

			for r in self.rows:
				newRow: List[str] = []
				for sublist in r:
					if isinstance(sublist, list):
						for item in sublist:
							newRow.append(self.stringify(item))
					else:
						newRow.append(self.stringify(sublist))
				flatRows.append(newRow)

		else:
			logging.warning("No logs to add to the csv file!")

		try:
			with open(self.outputPath, mode='w', encoding="utf-8") as csvFile:
				# Write the table header
				csvFile.write(TABLE_DELIMITER.join(self.csvHeadline))
				csvFile.write('\n')

				# Write all participants
				for r in flatRows:
					csvFile.write(TABLE_DELIMITER.join(r))
					csvFile.write('\n')

				# Write the legend
				csvFile.write('\n')
				csvFile.write('\n')
				csvFile.write('Legend')

				csvFile.write('\n')
				for name, levels in legend.items():
					levels.insert(0, name.replace(',', ' & '))
					csvFile.write(TABLE_DELIMITER.join(levels))
					csvFile.write('\n')

				csvFile.write('\n')
				csvFile.write(TABLE_DELIMITER.join(['GitHash', get_git_revision_hash()]))
				csvFile.write('\n')

				csvFile.write('\n')
				csvFile.write(TABLE_DELIMITER.join(['Time', str(self.startTime)]))
				csvFile.write('\n')
				
		except Exception:
			traceback.print_exc()

		print("Done, statistics exported as \"" + self.outputPath + "\".")

def convertTimestamp(timeStamp: Any) -> int:
	"""Convert a Python datetime into a timestamp in milliseconds."""
	if isinstance(timeStamp, datetime):
		return int(timeStamp.timestamp() * 1000)

	elif isinstance(timeStamp, int):
		return timeStamp

	else:
		raise TypeError("TimeStamp must either be a Python datetime object or an integer in millisecond format")


def getLevelAttributes(
			participant: StatsParticipant, 
			phaseName: str, 
			levelAttributes: List[Callable[[StatsParticipant, StatsPhase, StatsLevel], LEVEL_ATTRIB_T]], 
			levelHeader: List[str]
		) -> List[LEVEL_ATTRIB_T]:

	global warningLevelHeaderName
	global globalLevelIndex

	phase = participant.getPhaseByName(phaseName)
	output: List[LEVEL_ATTRIB_T] = []
	
	assert len(levelHeader) == len(levelAttributes), "Level Header and Level Attribute length mismatch: " + \
		str(len(levelHeader)) + "|" + str(len(levelAttributes)) + "!"

	# Prepare the legend
	groups = ','.join(participant.groups)
	if groups not in legend:
		legend[groups] = []

	# Prepare the level table header
	outLevelHeader: List[str] = []

	# Iterate over all levels in the specified phase
	i = 0
	for level in phase.levels:
		# Skip everything that is not a task
		if not level.isTask(): 
			continue

		i += 1
		globalLevelIndex += 1
		
		# Append the level name to the legend
		if level.name not in legend[groups]:
			legend[groups].append(level.name)

		# Make sure the level name matches the legend, because that information cannot be reconstructed in a later step
		assert level.name == legend[groups][globalLevelIndex - 1], "Fatal, the level name does not match the legend!"

		# Create the column header belonging to this entry
		outLevelHeader.extend([gLevelHeaderFormat % {
			'th': lh, 
			'levelIdx': i,
			'globalIdx': globalLevelIndex,
			'levelName': level.name,
			'phaseName': phase.name
		} for lh in levelHeader])

		# Get the entries
		for a in levelAttributes:
			entry = ">>> UNDEFINED <<<"
			try:
				entry = a(participant, phase, level)

			except Exception as e:
				entry = ">>> ERROR <<<"
				logging.error("Error while getting level attrib (" + getShortPseudo(participant.pseudonym) + "): " + str(e))
				logging.debug(traceback.format_exc())

			output.append(entry)

	# Display a warning if the program thinks the user messed up the header
	if not warningLevelHeaderName and not tmpHeader[len(tmpHeader)-1].startswith('LEVELS'):
		warningLevelHeaderName = True
		logging.warning("The header entry that will get replaced with the level header did not start with 'LEVELS' (" + \
			tmpHeader[len(tmpHeader)-1] + ")!")

	# Pop the LEVELS_... placeholder from the header and extend it with the levels header
	tmpHeader.pop(len(tmpHeader)-1)
	tmpHeader.extend(outLevelHeader)

	return output
