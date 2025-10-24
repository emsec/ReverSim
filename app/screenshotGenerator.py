import argparse
from dataclasses import dataclass
from datetime import datetime
import itertools
import logging
import os
import shutil
from typing import Callable, Iterable, Literal
import urllib.parse
import urllib.request
from flask import json

try:
	from playwright.sync_api import Playwright, Page, ConsoleMessage, sync_playwright
except:
	print("This script depends on Playwright to create the browser screenshots.") 
	print("Install it with `pip install playwright` or better `pip install -r requirementsDev.txt`")
	exit(-42)

try:
	from app.utilsGame import gfmSanitizeLink, gfmSanitizeLinkText, gfmSanitizeTable, gfmTitleToFragment, get_git_revision_hash, PhaseType
except ModuleNotFoundError:
	print("This script depends on `app.utilsGame` and `app.config`.")
	print("To resolve the dependency correctly, run the script as `python -m app.screenshotGenerator`")
	exit(-42)


"""Generate thumbnails for every level

NOTE: Don't forget to run `playwright install` after you have installed  
the dependencies from `requirementsDev.txt`.
"""

# --- Begin Config ---

WELCOME_TEXT = \
'''Welcome to the level library for [ReverSim](https://github.com/emsec/ReverSim)!

If you don't know the environment yet, here is a brief introduction. The full 
documentation can be found in the [accompanying GitHub repository](https://github.com/emsec/ReverSim).

ReverSim is an open-source environment for the browser, originally developed at the 
[Max Planck Institute for Security and Privacy (MPI-SP)](https://www.mpi-sp.org/)
to study human aspects in hardware reverse engineering.
The main objective is to reverse engineer a variety of Boolean circuits, each containing around 2 to 20 logic gates: 
Participants need to select the correct input values to achieve a set of predetermined output states by operating switches feeding the circuit.
For a valid solution, all lamp symbols in the circuit must be lit up and all danger signs must be turned off.

Circuits in ReverSim consist of eight basic elements:

| Icon                                                              | Description                                 |
| ---------------------------------------------------------------------- | ------------------------------------------- |
| <img src="./assets/battery.png" width="32" alt="Battery Icon">         | The battery is used to represent a logical 1. |
| <img src="./assets/switch_off_2.png" width="32" alt="Switch Icon">        | Switches are placed after a battery. The participant can open and close them to enter the correct inputs to the circuit. |
| <img src="./assets/and.png" width="32" alt="AND Gate">                 | Logic gate with the `AND` function. The output is high if all inputs are high. |
| <img src="./assets/or.png" width="32" alt="OR Gate">                   | Logic gate with the `OR` function. The output will be high if at least one input is high. |
| <img src="./assets/inverter.png" width="32" alt="Inverter Gate">       | Logic gate with the `Inverter` function. The output is low if the single input is high and vice versa. |
| <img src="./assets/bulb_on.png" width="32" alt="Lightbulb Icon">       | One of the two objectives. All lamps have to be ON in order to solve the level. |
| <img src="./assets/shocksign_gray.png" width="32" alt="Danger Sign Icon">   | One of the two objectives. All danger signs have to be OFF in order to solve the level. |
| <img src="./assets/questionMark.png" width="32" alt="Obfuscated Icon"> | The `Camouflaged` logic gate performing a function unknown to the participant (see details below). |

The icons for the logic gates are derived from the "distinctive shapes" set defined in [IEEE Std 91/91a-1991](https://en.wikipedia.org/wiki/Logic_gate#Symbols).
Gates are connected with wires to form the circuit. Any junctions are highlighted with a dot.

ReverSim implements two special types of logic gates for research on hardware obfuscation: `Camouflaged`
gates visually obscure their actual gate symbol.
`Covert` gates display a different icon that does
not match their actual logic function, and allow for "dummy inputs" that are visually connected but have no actual effect.
Circuits containing such gates are generally more challenging to reverse engineer. The following table lists the possible
combinations for the `Camouflaged` and `Covert` gates:

|                    | Covert Gate            | Camouflaged Gate          |
| ------------------ | ---------------------- | ------------------------- |
| Icon shown in circuit    | `AND`, `OR`            | `Camouflaged`             |
| Real function (Light blue text in this overview, not visible to the participant)    | `Inverter`, Wire       | `AND`, `OR`               |
| Supports dummy inputs?      | Yes                    | No                        |

Further details about task design and elements are available in the
[level documentation](https://github.com/emsec/ReverSim/blob/main/doc/Level.md#covertgate).

A manual for the tool that was used to generate this level library page is available in the
[screenshot generator documentation](https://github.com/emsec/ReverSim/blob/main/doc/ScreenshotGenerator.md).
'''

JSON_INDENTATION = '    '

base_url = "http://127.0.0.1:8000"
base_input_path: str = 'examples/conf/assets/levels/differentComplexityLevels'
base_output_path: str = 'doc/levels'
pseudonym: str = 'd15bffa801e8d5e26a870c020d7a4a73'

groups: list[str] = []

PHASES_WITH_LEVEL_LIST = [PhaseType.Quali, PhaseType.Competition, PhaseType.Skill]

TAG_TO_ICON = {
	"hasTimeLimit": "⏰",
	"hasRandomSwitch": "🎲",
	"hasObfuscation": "❓"
}

# The script will copy these files to the output directory in the asset subfolder
RESSOURCE_DEPENDENCIES = [
	"doc/res/elements/battery.png",
	"doc/res/elements/switch_off_2.png",
	"doc/res/elements/and.png",
	"doc/res/elements/or.png",
	"doc/res/elements/inverter.png",
	"doc/res/elements/bulb_on.png",
	"doc/res/elements/shocksign_gray.png",
	"doc/res/elements/questionMark.png"
]

md_title = 'ReverSim - Level Library'

# --- End Config ---

NL = '\n'
ENCODING = 'UTF-8'
DOT_SLASH = os.path.curdir + os.path.sep

isGroupMode = lambda: len(groups) > 0

@dataclass
class LevelInfo:
	levelName: str
	stats: dict[str, int]
	tags: list[str]
	solutions: dict[
		Literal['switchIDs', 'initialSwitchStates', 'correctSolutions', 'minHD'], list[str] | list[int] | int
	]

levelInfos: dict[str, LevelInfo] = {}

expectedLevels: set[str] = set()


def downloadCanvasImage(page: Page, outputName: str):
	"""Select the canvas, take a screenshot and save it to disk"""
	# Craft the path and create all folders
	
	os.makedirs(os.path.dirname(outputName), exist_ok=True)

	# Select the image
	canvas = page.query_selector('canvas')
	assert canvas is not None, "No Canvas found"

	# Save the image to disk
	image_b64 = canvas.evaluate("canvas => canvas.toDataURL('png')")
	resp = urllib.request.urlopen(image_b64)
	with open(outputName, 'wb') as f:
		f.write(resp.file.read())

	logging.debug(f'Screenshot saved: "{outputName}"')


def handleLog(msg: ConsoleMessage):
	"""The browser will send the level stats to the console, this method extracts the data and writes it to a dict.
	
	Since the events might fire asynchronously, we use the level name inside the stats dict to determine from 
	which level this event was fired.
	"""
	global levelInfos

	# Gather the fileName from URL
	try:
		query = urllib.parse.urlparse(msg.page.url).query #type: ignore
		fileName = urllib.parse.parse_qs(query).get('level')
	except:
		fileName = '?Unknown Level?'

	# Playwright does not properly stringify JavaScript objects, therefore do it manually
	try:
		if len(msg.args) > 0:
			message = msg.args[0].evaluate("x => typeof x === 'string' || x instanceof String ? x : JSON.stringify(x)")
		else:
			message = msg.text.strip()
		
	except Exception as e:
		logging.error(f'Unable to stringify object: "{str(e)}"')
		message = msg.text.strip()

	# Check if message looks like an error, if yes throw a warning
	if message.startswith("Err"):
		logging.warning(f'"{fileName}": "{message.splitlines()[0]}"')
		return

	# Sort out everything that does not look like JSON
	if not message.startswith('{"'):
		return

	# The level stats object should contain the key "name"
	stats = json.loads(message)
	if "name" in stats:
		# Generate stats
		currentLevel: str = stats['name']

		# Generate Tags
		tags: dict[str, bool] = {
			"hasTimeLimit": stats["timeLimit"] > 0, # type: ignore
			"hasRandomSwitch": stats["numSwitchesRand"] > 0, # type: ignore
			"hasObfuscation": stats["numObfuscated"] > 0 # type: ignore
		}

		# Build the level info object from name, tags and stats
		levelInfos[currentLevel] = LevelInfo(
			levelName=currentLevel,
			stats=stats,
			tags=list(itertools.compress(tags.keys(), tags.values())),
			solutions=stats['solutions']
		)

		# Make sure that the level name inside the stats dict matches the expected level, afterwards delete it
		# as the parent class already holds that information
		assert levelInfos[currentLevel].stats['name'] == currentLevel, \
			f"Event handler out of sync, {levelInfos[currentLevel].stats['name']} != {currentLevel}"
		del levelInfos[currentLevel].stats['name']
		del levelInfos[currentLevel].stats['solutions']

	# When parsing went wrong, the object will contain "message" in most cases
	elif "message" in stats:
		logging.warning(f'"{fileName}": "{stats["message"]}"')


def screenshotLevel(page: Page, levelName: str):
	"""Navigate the page to the desired level and make sure it is shown"""
	global currentLevel
	currentLevel = levelName

	try:
		outputPath = os.path.join(base_output_path, 'screenshots', currentLevel) + ".png"

		#if os.path.exists(outputPath):
		#	print(f'Skipping: "{outputPath}"')
		#	return

		quotedLevelName = urllib.parse.quote_plus(currentLevel)
		page.goto(f'{base_url}/game?group=viewer&lang=en&ui={pseudonym}&level={quotedLevelName}')
		page.wait_for_timeout(500)

		downloadCanvasImage(page, outputName=outputPath)
	
	except Exception as e:
		if str(e) == "No Canvas found":
			logging.error("No canvas found, does the pseudonym you specified really exist?")
		elif 'CONNECTION_REFUSED' in str(e):
			logging.error("Connection Refused, is the server running?")
		else:
			logging.exception(f'Failed to screenshot: "{str(e)}"')


def writeJson(levelInfos: dict[str, LevelInfo], fileName: str = 'Level_Index.json'):
	"""Open and write all level infos and screenshots to a json file (including metadata)"""
	firstLine = True

	logging.debug(f'Writing "{base_output_path}/{fileName}"')
	with open(os.path.join(base_output_path, fileName), mode='tw', encoding=ENCODING) as jsonFile:
		# Create the preamble
		jsonFile.write('{' + NL)
		jsonFile.writelines(jsonPreambleWriter())

		# Write all level info blocks
		jsonFile.write(JSON_INDENTATION + '"levels": {' + NL)
		for _, levelInfo in levelInfos.items():
			if not firstLine:
				jsonFile.write(',' + NL)
			
			# Dump level infos merged with tags
			assert '"' not in levelInfo.levelName, "JSON field contains double quote"
			line = json.dumps({
				levelInfo.levelName: {**levelInfo.stats, "tags": levelInfo.tags, "solutions": levelInfo.solutions}
			}).removeprefix('{').removesuffix('}')
			jsonFile.write(JSON_INDENTATION + JSON_INDENTATION + line)
			firstLine = False

		# Close all open brackets
		jsonFile.write(NL + JSON_INDENTATION + '}' + NL + '}' + NL)
	

def writeMarkdown(levelNames: Iterable[str], fileName: str = 'Readme.md'):
	"""Open and write all level infos and screenshots to a markdown file (including header)"""
	logging.debug(f'Writing "{base_output_path}/{fileName}"')
	with open(os.path.join(base_output_path, fileName), mode='tw', encoding=ENCODING) as mdFile:
		# https://github.github.com/gfm
		mdFile.writelines(markdownPreambleWriter())
		mdFile.write("# Level Library" + NL)
		mdFile.write(WELCOME_TEXT + NL + NL)
		mdFile.write('## Level Overview' + NL)
		mdFile.writelines(markdownTocWriter(levelNames))
		mdFile.write(NL)
		mdFile.write('## Screenshots' + NL)
		mdFile.writelines(markdownScreenshotWriter(levelNames))


def jsonPreambleWriter(now: datetime = datetime.now()):
	"""Yield the metadata that is stored in the json about the current run."""
	yield f'{JSON_INDENTATION}"date": {now.timestamp()},{NL}'
	yield f'{JSON_INDENTATION}"generatorVersion": "{get_git_revision_hash(shortHash=True)}",{NL}'
	if isGroupMode():
		yield f'{JSON_INDENTATION}"groups": {json.dumps(groups)},{NL}'
	else:
		yield f'{JSON_INDENTATION}"folder": "{base_input_path}",{NL}'


def markdownPreambleWriter(now: datetime = datetime.now()):
	"""Yield a yml preamble for a markdown file containing the time created."""
	yield '---' + NL
	yield f'title: {md_title}' + NL
	yield f'date: {datetime.strftime(now, "%d.%m.%Y %H:%M")}{NL}'
	yield f'generatorVersion: {get_git_revision_hash(shortHash=True)}{NL}'
	if isGroupMode():
		yield f'groups: {", ".join(groups)}{NL}'
	else:
		assert "'" not in str(base_input_path), "Invalid YAML syntax"
		yield f"folder: '{base_input_path}'{NL}"
	yield '---' + NL + NL


def markdownWelcomeWriter():
	yield


def markdownTagWriter(tags: list[str]) -> str:
	tagToIcon: Callable[[str], str] = lambda tag: TAG_TO_ICON[tag] if tag in TAG_TO_ICON else tag
	return ', '.join(tagToIcon(tag) for tag in tags)


def markdownTocWriter(levelNames: Iterable[str]):
	"""Yield a markdown table containing all levels.
	
	- with a hyperlink to the screenshots
	- their respective stats
	"""
	keys = None
	BLACKLIST = ["numSwitchesRand"]

	for levelName in levelNames:
		stats = {k: v for k, v in levelInfos[levelName].stats.items() if k not in BLACKLIST}

		# Generate the table header this is the first row
		if keys is None:
			keys = stats.keys()
			yield f'| Name | {" | ".join([k.removeprefix("num") for k in keys])} | tags |' + NL
			yield f'| :--- | {" | ".join(["---" for _ in keys])} | --- |' + NL

		# Otherwise sanity check that the key format never changes 
		else:
			pass #assert stats.keys()

		# Generate a table row
		yield (f'| [{gfmSanitizeLinkText(levelName)}]({gfmTitleToFragment(levelName)}) | ' # Name with link
			f'{" | ".join([gfmSanitizeTable(str(s)) for s in stats.values()])}' # Stats
			f' | {markdownTagWriter(levelInfos[levelName].tags)} |{NL}' # Tags
		)
	
	yield f'{NL}**Legend:** {NL}'
	yield '- ⏰: Has time limit' + NL 
	yield '- 🎲: some switch states are initialized randomly' + NL
	yield '- ❓: contains camouflage/covert elements' + NL


def markdownScreenshotWriter(levelNames: Iterable[str]):
	"""Yield a markdown header and image for every level."""
	yield f'The following screenshots of the levels will contain some annotations that are not shown in ReverSim:{NL}'
	yield f'- The name of the level is displayed in light orange in the top left corner{NL}'
	yield f'- The ID of the switches are displayed in light blue, so you can better understand which switch was clicked when looking at the log files{NL}'
	yield f'- The switches are in the starting position as defined in the level file. If the initial switch position will be random, a dice icon 🎲 is shown on the switch.{NL}'
	yield f'- The actual function of covert/camouflage gates is written in blue letters on top of the visual gate icon{NL}{NL}'

	for levelName in levelNames:
		levelInfo = levelInfos[levelName]
		stats: dict[str, int|str] = \
			{**levelInfo.stats, "tags": markdownTagWriter(levelInfo.tags)}
		correctSolutions = str(levelInfo.solutions["correctSolutions"]).replace("'", "`")[1:-1]
		yield f'### {levelName}{NL}'
		yield f'![Screenshot of "{gfmSanitizeLinkText(levelName)}"]({gfmSanitizeLink("screenshots/"+levelName+".png")}){NL}{NL}'
		yield f'{", ".join([f"_{k}_: {v}" for k, v in stats.items() if len(str(v)) > 0])}{NL}{NL}'
		yield f'Correct solutions for Switch IDs {levelInfo.solutions["switchIDs"]}: {correctSolutions}{NL}{NL}'


def getLevelsFromGroup(groupNames: list[str]):
	"""Get all slides of type level for the specified list of groups"""
	from app.utilsGame import getFileLines
	from app.model.Level import Level
	from app.config import LEVEL_ENCODING, REMAP_LEVEL_TYPES
	import app.config as gameConfig
	gameConfig.loadGameConfig()

	global base_input_path
	base_input_path = Level.getBasePath(type='level')

	remapLevelType: Callable[[str], str] = lambda type: REMAP_LEVEL_TYPES[type] if type in REMAP_LEVEL_TYPES else type

	# Iterate over all groups
	for g in groupNames:
		group = gameConfig.getGroup(g)

		# Iterate over all Phases that contain level lists
		for p in filter(lambda p: p in PHASES_WITH_LEVEL_LIST, group['phases']):
			phase = group[p]
			assert 'levels' in phase, "The Phase block is missing required key 'levels'"
			
			# Convert levels to a list if not already one
			levelLists = phase['levels'] if isinstance(phase['levels'], list) else [phase['levels']]

			# Iterate over all level lists
			for l in levelLists:
				fileContent = getFileLines(Level.getBasePath('levelList'), l, encoding=LEVEL_ENCODING)

				# Iterate over all lines skipping everything that is not a level
				for levelType, levelName in fileContent:
					if remapLevelType(levelType) != 'level':
						continue

					yield levelName


def getLevelsFromPath(path: str):
	"""Yield all level files in the specified folder"""
	# Recursively list the level files in all folders & subfolders
	for folder, _, levels in os.walk(path):
		for l in levels:
			# Splice the parent folder and level file name together and remove all './' occurrences
			level = l.removeprefix(DOT_SLASH)
			parentFolder = os.path.relpath(path=folder, start=base_input_path)
			levelPath = os.path.join(parentFolder, level)
			yield levelPath.removeprefix(DOT_SLASH)


def run(playwright: Playwright):
	global jsonFile, levelInfos

	# launch the browser and open a new browser page
	browser = playwright.chromium.launch()
	page = browser.new_page()
	page.on("console", lambda msg: handleLog(msg))

	if len(groups) > 0:
		levels = getLevelsFromGroup(groups)
	else:
		levels = getLevelsFromPath(base_input_path)

	# Iterate over all levels from this source and generate screenshots (skipping duplicates)
	for l in levels:
		currentLevel = l.replace('\\', '/')
		if currentLevel in levelInfos:
			continue

		expectedLevels.add(currentLevel)
		screenshotLevel(page, currentLevel)

	# Report if levels errored out or if the console log event handler messed something up
	sanityCheck = expectedLevels.difference(levelInfos.keys())
	if len(sanityCheck) > 0:
		logging.warning(f'The following levels could not be loaded: {str(sanityCheck)}!')

	# NOTE If no levels where loaded, the output folder might not exist, therefore skip writing an empty index
	if len(levelInfos) > 0:
		# Write JSON Index File
		writeJson(levelInfos)

		# Write Markdown Index File
		# By default the levels are sorted by their folder
		sortedNames = levelInfos.keys() #sorted(levelInfos.keys())
		writeMarkdown(sortedNames)

		# Create the static asset folder needed by the Readme and copy all necessary resources
		try:
			ASSET_FOLDER = os.path.join(base_output_path, 'assets')
			os.makedirs(ASSET_FOLDER, exist_ok=True)
			for asset in RESSOURCE_DEPENDENCIES:
				shutil.copy(asset, ASSET_FOLDER)

		except Exception as e:
			logging.error(f'Could not copy static assets for Readme.md: "{str(e)}"')

	else:
		logging.warning(
			"The list of successfully loaded levels is empty, therefore no Markdown/JSON index will be generated!"
		)	
	
	# always close the browser
	browser.close()


# Main program entry Point
if __name__ == '__main__':
	print() # Create a newline at the beginning, to make the output more readable in a VS Code Powershell
	parser = argparse.ArgumentParser(description='This script generates screenshots for all ReverSim Levels you provide.')
	parser.add_argument('pseudonym', help='A pregenerated pseudonym that was assigned to a group with the viewer scene.')
	parser.add_argument("-l", "--log", metavar='LEVEL', default="DEBUG",
		help="Specify the log level, must be one of DEBUG, INFO, WARNING, ERROR or CRITICAL"
	)
	parser.add_argument('-b', '--base-url', default=base_url, 
		help=('The url of a running instance of the game. Defaults to localhost. Since the server loads the level '
		 	'lists from disk and does not request them from the server, this will rarely be changed.')
	)
	parser.add_argument('-o', '--output', default=base_output_path, 
		help=('The output folder where the screenshots and Markdown/JSON Index will be written to. Defaults to '
			f'"{base_output_path}"')
	)

	# You can either load levels from a list of groups, or by specifying a path on disk. Not both
	parserGroup = parser.add_mutually_exclusive_group()
	parserGroup.add_argument('-g', '--group', action='append', default=[],
		help='Include all levels from this group in the output. Repeat this option to add multiple groups.'
	)
	parserGroup.add_argument('-p', '--path', default=base_input_path,
		help=f'Generate the output from all levels in this folder. Defaults to "{base_input_path}"'
	)
	
	args = parser.parse_args()
	try:
		logLevel = getattr(logging, args.log.upper())
	except Exception as e:
		print("Invalid log level: " + str(e))
		exit(-1)

	logging.basicConfig(
		format='[%(levelname)s] %(message)s',
		level=logLevel,
	)

	pseudonym = args.pseudonym
	groups = [g.strip().casefold() for g in args.group]
	base_input_path = args.path.strip()
	base_url = args.base_url.strip()
	base_output_path = args.output.strip()

	if len(groups) > 0:
		logging.info(f'Generating screenshots for groups: [{", ".join(groups)}]')
	else:
		logging.info(f'Generating screenshots for path: "{base_input_path}"')

	try:
		logging.info(f'Starting Browser and trying to connect to "{base_url}"')
		with sync_playwright() as playwright:
			run(playwright)

		logging.info(f"Done, rendered {len(levelInfos)} screenshots!")

	# Catch the user requests to exit event
	except KeyboardInterrupt:
		logging.info("Received Keyboard Interrupt, Exiting!")
