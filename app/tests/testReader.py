from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional, Union
from app.statistics.staticConfig import TABLE_DELIMITER, LevelStatus
from app.statistics.statisticUtils import removesuffix
from app.statistics.statistics2 import LOGFILE_LOCATION
from app.utilsGame import getFileLines, getShortPseudo

import app.config as gameConfig

versions = {}
gitHashs = {}

errorVersions = {}

def verifyParticipant(csvPath: str):
	problems = 0

	with open(csvPath, mode="r", encoding="utf-8") as f:
		tableHeader = None
		legendFound = False

		levelOrder: Dict[str, List[str]] = {}

		fileLines = f.readlines()

		# First search the legend
		for i, line in enumerate(fileLines):
			entries = [x.strip() for x in line.split(TABLE_DELIMITER)]

			# Skip over empty lines
			if len(entries) < 1 or len(entries[0]) < 1: continue

			# Go ahead until the legend is found
			if not legendFound:
				legendFound = entries[0].casefold() == 'legend'
				continue
			
			# Gather the level order from the legend
			levelOrder[entries[0]] = entries[1:]

		# Second parse the participants
		for i, line in enumerate(fileLines):
			pseudonym = None
			try:
				entries = [x.strip() for x in line.split(TABLE_DELIMITER)]

				# Skip over empty lines
				if len(entries) < 1 or len(entries[0]) < 1: continue
				
				# Parse the table header
				if i == 0:
					tableHeader = entries
					continue
				
				# Break at the legend
				if entries[0].casefold() == 'legend':
					break

				# Read in the log file for this participant (this data should be valid)
				pseudonym = entries[0]
				groups, phases, levels, skillScore = generateStatistics(pseudonym)
				
				assert tableHeader is not None

				# Perform global checks
				if skillScore is not None:
					assert str(skillScore) == entries[tableHeader.index('Score Skillasessment')], "Expected score %d, got %s after SkillAsessment" % (skillScore, entries[tableHeader.index('Score Skillasessment')])

				# Perform per level checks
				for name, stats in levels.items():
					if stats['status'] != LevelStatus.SOLVED:
						continue

					i = levelOrder[' & '.join(groups)].index(removesuffix(name, '.txt')) + 1
					assert isinstance(stats['startTime'], int) and isinstance(stats['endTime'], int)
					duration = stats['endTime'] - stats['startTime']
					assert(duration > 0)

					assert str(stats['switchClicks']) == entries[tableHeader.index('Number of switch clicks (%d)' % i)], "Expected %d switch clicks, got %s in level %s!" % (stats['switchClicks'], entries[tableHeader.index('Number of switch clicks (%d)' % i)], name)
					assert str(stats['minSwitchClicks']) == entries[tableHeader.index('Minimum switch clicks (%d)' % i)], "Expected %d min switch clicks, got %s in level %s!" % (stats['minSwitchClicks'], entries[tableHeader.index('Minimum switch clicks (%d)' % i)], name)
					#assert str(stats['confirmClicks']) == entries[tableHeader.index('Number of confirm clicks (%d)' % i)], "Expected %d confirm clicks, got %s in level %s!" % (stats['confirmClicks'], entries[tableHeader.index('Number of confirm clicks (%d)' % i)], name)
					#assert duration == int(float(entries[tableHeader.index('Time spent (%d)' % i)])*1000), "Expected time %.2f, got %s in level %s!" % (float(duration/1000), entries[tableHeader.index('Time spent (%d)' % i)], name)
					#assert level['']

			except AssertionError as e:
				problems += 1
				print(getShortPseudo(str(pseudonym)) + ": " + str(e))

	print('Problems found: %d' % problems)


def generateStatistics(pseudonym: str):
	"""Load a players logfile and use a crude parser to generate some key statistics"""
	parsedFile = parseLogfile(os.path.join(LOGFILE_LOCATION, 'logFile_%s.txt' % (pseudonym)))

	#parsedFile.sort(key=lambda k: k["Time"])

	groups: List[str] = []
	phases: List[Dict[str, Any]] = []
	levels: Dict[str, Dict[str, Union[int, LevelStatus, str]]] = {}
	activeLevel: Optional[str] = None
	activePhase: Optional[str] = None
	version = "None"
	gitHash = "None"

	score: Optional[float] = None

	for event in parsedFile:
		assert isinstance(event['Event'], str)
		assert isinstance(event['Time'], datetime)

		if event['Event'] == 'Created Logfile':
			version = event.get('Version', '0.1.0')
			gitHash = event.get('GitHashS', 'N/S')

			if version not in versions: versions[version] = 0
			if gitHash not in gitHashs: gitHashs[gitHash] = 0

			versions[version] += 1 # type: ignore
			gitHashs[gitHash] += 1 # type: ignore

		# group assignment
		if event['Event'] == 'Group Assignment':
			groups.append(event['Group'])
		
		# phase loaded
		elif event['Event'] == 'change in Scene':
			phases.append({
				"name": event['Scene']
			})
			activeLevel = None
			activePhase = event['Scene']

		# level loaded
		elif event['Event'] == 'new Level':
			assert isinstance(event['Filename'], str)
			activeLevel = event['Filename']
			levels[activeLevel] = {
				"switchClicks": 0,
				"minSwitchClicks": -1,
				"confirmClicks": 0,
				"cconfirmClicks": -1,
				"startTime": int(event['Time'].timestamp()*1000),
				"firstTryTime": -1,
				"endTime": -1,
				"status": LevelStatus.LOADED,
				"phase": str(activePhase)
			}

		# level started
		elif event['Event'] == 'Loaded' and event['Type'] == 'Level':
			assert activeLevel is not None
			levels[activeLevel]['startTime'] = int(event['Time'].timestamp()*1000)
			levels[activeLevel]['status'] = LevelStatus.INPROGRESS
			levels[activeLevel]['confirmClicks'] = 0
			levels[activeLevel]['cconfirmClicks'] = -1
		
		# switch and confirm click
		elif event['Event'] == 'Click':
			if event['Object'] == 'Switch' and activeLevel is not None:
				assert isinstance(levels[activeLevel]['switchClicks'], int)
				levels[activeLevel]['switchClicks'] += 1 # type: ignore

			elif event['Object'] == 'ConfirmButton':
				assert activeLevel is not None, "No level is active"
				assert isinstance(levels[activeLevel]['confirmClicks'], int)
				#levels[activeLevel]['confirmClicks'] += 1 # type: ignore
				levels[activeLevel]['confirmClicks'] += 1 # type: ignore
				
				# Time first try
				if levels[activeLevel]['firstTryTime'] == -1:
					levels[activeLevel]['firstTryTime'] = int(event['Time'].timestamp()*1000)

		# level feedback dialogue
		elif {'Event': 'Pop-Up displayed', 'Content': 'Feedback about Clicks'}.items() <= event.items():
			assert activeLevel is not None
			confirmClicks = int(event['Nmbr Confirm Clicks'])
			levels[activeLevel]['cconfirmClicks'] = confirmClicks
			#levels[activeLevel]['confirmClicks'] = confirmClicks

			#if confirmClicks != levels[activeLevel]['confirmClicks']:
			#	print(pseudonym[:16] + ": Client reported " + str(levels[activeLevel]['confirmClicks']) + " confirm clicks, server recoreded " + str(confirmClicks) + "!")

			levels[activeLevel]['status'] = LevelStatus.SOLVED
			levels[activeLevel]['minSwitchClicks'] = int(event['Optimum Switch Clicks'])
			levels[activeLevel]['endTime'] = int(event['Time'].timestamp()*1000)

			# Time first try
			if levels[activeLevel]['firstTryTime'] == -1:
				levels[activeLevel]['firstTryTime'] = int(event['Time'].timestamp()*1000)

		# Skill asessment finished
		elif event['Event'] == 'SkillAssessment':
			group = groups[len(groups)-1]
			levelListPath = gameConfig.getGroup(group)[str(activePhase)]['levels']
			levelList = getFileLines(levelListPath, encoding=gameConfig.LEVEL_ENCODING)
			point_map = {
				"low": 1,
				"medium": 4,
				"high": 8,
				"guru": 12
			}

			scoreInLog = int(event['Score'])

			# "difficulty weighted points over time for first-attempt correct solution" metric
			score = 0
			for levelName, levelStats in filter(lambda l: l[1]["status"] == LevelStatus.SOLVED and l[1]["phase"] == activePhase and l[1]["confirmClicks"] == 1, levels.items()):
				assert isinstance(levelStats["startTime"], int)
				assert isinstance(levelStats["endTime"], int)

				fullPath = [name for lt, name in levelList if name.endswith(levelName)]
				dir = fullPath[0].split("/", 1)[0]

				points = point_map.get(dir, 0)
				time = (levelStats["endTime"] - levelStats["startTime"])/1000
				score += 100*points/max(time, 1)
			score = round(score)

			if score != scoreInLog:
				if version not in errorVersions: errorVersions[version] = 0
				errorVersions[version] += 1 # type: ignore

			#print("Participant: " + pseudonym[:16] + "Score: " + str(score))
			# Insane Debug Line to find issue #92
			# [(name, 100*point_map.get([n for lt, n in levelList if n.endswith(name)][0].split("/", 1)[0], 0)/max((stats["endTime"] - stats["startTime"])/1000, 1), stats["confirmClicks"], stats["cconfirmClicks"], stats["status"].name) for name, stats in levels.items() if stats["phase"] == "Skill"]
			# round(sum([100*point_map.get([n for lt, n in levelList if n.endswith(name)][0].split("/", 1)[0], 0)/max((stats["endTime"] - stats["startTime"])/1000, 1) for name, stats in levels.items() if stats["phase"] == "Skill" and stats["status"] == LevelStatus.SOLVED and stats["confirmClicks"] == 1]))

	return groups, phases, levels, score


def parseLogfile(filePath: str) -> List[Dict[str, Any]]:
	parsedFile: List[Dict[str, Any]] = []

	with open(filePath, mode="r", encoding="utf-8") as f:
		event: Dict[str, Any] = {}

		for line in f:
			if line.startswith(('\r', '\n')):
				if len(event) > 0:
					assert 'Time' in event and 'Event' in event, str(event)
					parsedFile.append(event)
					event = {}

				continue

			split = line.strip('§').split(':', 1)
			key, value = [x.strip() for x in split]
			event[key] = parseTime(value) if key == 'Time' else value

		# Dump the last entry
		if 'Time' in event and 'Event' in event:
			parsedFile.append(event)

	return parsedFile


def parseTime(timeString: str) -> datetime:
	if timeString.isdecimal():
		assert float(timeString) > 0.0, "Could not convert unix time, must be a number greater than zero!"
		return datetime.fromtimestamp(float(timeString)/1000, tz=timezone.utc) # time comes in thousands of a second
	else:
		assert timeString.count(':') == 2
		cleanedTime = ''.join(c for c in timeString if c in [':', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'])
		h, m, s = [int(x) for x in cleanedTime.split(':')]
		if 'PM' in timeString or '下午' in timeString:
			if h != 12:
				h += 12
			assert (h < 24), "Hour is > 24: " + str(h) + ", " + timeString
		elif 'AM' in timeString or '上午' in timeString:
			if h == 12:
				h = 0
			assert (h < 12), "Hour is > 12: " + str(h) + ", " + timeString
		return datetime(year=1970, month=1, day=1, hour=h, minute=m, second=s, tzinfo=timezone.utc)	


# program entry point
# NOTE: Minimum Python Version: 3.6
if __name__ == "__main__":
	gameConfig.loadGameConfig()

	verifyParticipant('statistics_glurak.csv')

	print(versions)
	print("")
	print(errorVersions)
	print('Done')
