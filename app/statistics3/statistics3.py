import argparse
from datetime import datetime
import json
import logging
import os
from pathlib import Path
from typing import Iterable

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

import app.config as gameConfigLegacy
from app.gameConfig import GameConfig
from app.model.LevelLoader.JsonLevelList import JsonLevelList
from app.model.LevelLoader.LevelLoader import LevelLoader
from app.model.LogEvents import GroupAssignmentEvent, LogEvent
from app.model.Participant import Participant
from app.statistics3.GameStateValidator import GameStateValidator
from app.statistics3.LogEventValidator import LogEventValidator
from app.statistics3.statisticsUtils import LogValidationError, StatisticJSONEncoder
from app.statistics3.StatsParticipant import StatsParticipant
from app.utilsGame import get_git_revision_hash, getShortPseudo

# Flask uses an instance folder to store and load assets
INSTANCE_FOLDER = os.path.abspath(os.environ.get('REVERSIM_INSTANCE', './instance'))

# paths are relative to instance folder
CONFIG_NAME = os.environ.get('REVERSIM_CONFIG', 'conf/gameConfig.json')
DATABASE_PATH = os.environ.get('REVERSIM_DATABASE', 'statistics/reversim.db')

start_time: datetime = datetime.now()
error_pseudonyms: dict[str, str] = {}

class StatisticsGenerator:
	def __init__(self, 
		instance_path: str, 
		gameConfig: GameConfig,
		levelLoader: type[LevelLoader],
		database: Engine
	) -> None:
	
		self.instance_path = instance_path
		self.gameConfig = gameConfig
		self.levelLoader = levelLoader
		self.engine = database


	def read_group(self, group: str, skip_debug: bool = True, start_time: datetime|None = None) -> Iterable[StatsParticipant]:
		logging.info(f'Querying all participants for group {group}')

		with Session(self.engine) as session:
			stmt = select(GroupAssignmentEvent.pseudonym).where(
				GroupAssignmentEvent.group == group
			)

			if skip_debug:
				stmt = stmt.where(GroupAssignmentEvent.isDebug == False) # noqa: E712

			if start_time is not None:
				stmt = stmt.where(GroupAssignmentEvent.timeServer >= start_time)
			
			loaded_pseudonyms: list[str] = list(session.scalars(stmt))
			expected_pseudonyms: list[str] = []
			valid_pseudonyms: list[str] = []

			for pseudonym in loaded_pseudonyms:
				try:
					player = session.get_one(Participant, pseudonym)

					# Drop all players that have not started the game
					if not player.startedGame:
						continue
					
					expected_pseudonyms.append(pseudonym)
					participant = self.read_participant(session, player)
					valid_pseudonyms.append(pseudonym)
					yield participant

				except LogValidationError as e:
					eventID: int|None = e.event.id if e.event is not None else None
					lineInfo = (f'#{eventID}' if eventID is not None else '')
					logging.error(f'{getShortPseudo(pseudonym)}{lineInfo} is invalid: "{e}"')
					error_pseudonyms[pseudonym] = f'{eventID}: "{e}"'

				except AssertionError as e:
					logging.error(f'Something went wrong while parsing {pseudonym}: "{e}"')
					error_pseudonyms[pseudonym] = f'Assertion: "{e}"'

			logging.info(' ------------ ')
			logging.info(f'{len(valid_pseudonyms)} of {len(expected_pseudonyms)} player logs passed validation')

	
	def read_participant(self, session: Session, player: Participant) -> StatsParticipant:
		statsParticipant = StatsParticipant(
			pseudonym=player.pseudonym,
			is_debug=player.isDebug
		)

		events = session.execute(
			statement=select(LogEvent).where(LogEvent.pseudonym == statsParticipant.pseudonym)
		).scalars()

		log_validator = LogEventValidator()
		state_validator = GameStateValidator()

		logging.info(f'Validating {getShortPseudo(player.pseudonym)}')
		for event in events:
			try:
				log_validator.handle_event(event, session, statsParticipant, player)
			
			# Add the originating event of this error the the exception
			except LogValidationError as e:
				e.event = event
				raise e

		state_validator.validate(statsParticipant, session)

		# If all went well, we have a populated player statistic
		return statsParticipant


def main():

	parser = argparse.ArgumentParser(description="A script to aggregate the logfiles from the ReverSim game into a csv file.")
	parser.add_argument('-i', '--instance-path', help='', default=INSTANCE_FOLDER)
	parser.add_argument("-o", "--output", help="The filename of the output statistic csv file", default='statistics.csv')
	#parser.add_argument("-s", "--skipScreenshots", help="Skip the screenshot validation", action="store_true")
	parser.add_argument("-d", "--allowDebug", help="Allow debug groups to end up in the output", action="store_true")
	parser.add_argument("-l", "--log", metavar='LEVEL', help="Specify the log level, must be one of DEBUG, INFO, WARNING, ERROR or CRITICAL", default="INFO")
	parser.add_argument('-b', '--beginning', help='Only include logs that start after this date in ISO 8601 format, e.g. 2026-01-15', default=None)
	
	args = parser.parse_args()

	# Parse log level and set it
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

	# Load the GameConfig
	gameConfig = GameConfig(
		configName=CONFIG_NAME,
		instanceFolder=args.instance_path
	)
	gameConfigLegacy.setGameConfig(gameConfig)
	

	# Load the Level Loader
	JsonLevelList.singleton = JsonLevelList.fromFile(instanceFolder=args.instance_path)

	# Open the Database
	database_path = os.path.join(args.instance_path, DATABASE_PATH)
	engine = (create_engine("sqlite:///" + database_path, echo=False)
		.execution_options(sqlite_readonly = True))
	
	try:
		if args.beginning is not None and len(args.beginning.strip()) > 0:
			start_time = datetime.fromisoformat(args.beginning.strip())
		else:
			start_time = None
	except Exception as e:
		logging.error(e)
		return

	statsGenerator = StatisticsGenerator(args.instance_path, gameConfig, JsonLevelList, engine)
	data = list(statsGenerator.read_group(
		group='cognitive_obfuscation',
		skip_debug=not args.allowDebug,
		start_time=start_time
	))
	
	gitHash = None
	try:
		gitHash = get_git_revision_hash(shortHash=True)
	except Exception as e:
		logging.warning('Could not determine git hash: ' + str(e))

	end_time = datetime.now()
	data_json = json.dumps({
		'start_time': start_time,
		'end_time': end_time,
		'gitHash': gitHash,
		'args': vars(args),
		'instance': INSTANCE_FOLDER,
		'participants': data,
		'errors': error_pseudonyms
	}, cls=StatisticJSONEncoder, indent=4)

	Path(f'statistics_{end_time.strftime('%Y-%m-%d_%H%M')}.json').write_text(data_json, encoding='UTF-8')

if __name__ == '__main__':
	main()
