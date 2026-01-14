import argparse
import logging
import os
from typing import Iterable

from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

import app.config as gameConfigLegacy
from app.gameConfig import GameConfig
from app.model.LevelLoader.JsonLevelList import JsonLevelList
from app.model.LevelLoader.LevelLoader import LevelLoader
from app.model.LogEvents import GroupAssignmentEvent, LogEvent
from app.model.Participant import Participant
from app.statistics3.GameStateValidator import GameStateValidator
from app.statistics3.LogEventValidator import LogEventValidator
from app.statistics3.statisticsUtils import LogValidationError
from app.statistics3.StatsParticipant import StatsParticipant
from app.utilsGame import getShortPseudo

# Flask uses an instance folder to store and load assets
INSTANCE_FOLDER = os.path.abspath(os.environ.get('REVERSIM_INSTANCE', './instance'))

# paths are relative to instance folder
CONFIG_NAME = os.environ.get('REVERSIM_CONFIG', 'conf/gameConfig.json')
DATABASE_PATH = os.environ.get('REVERSIM_DATABASE', 'statistics/reversim.db')


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


	def read_group(self, group: str, skip_debug: bool = True) -> Iterable[StatsParticipant]:
		logging.info(f'Querying all participants for group {group}')

		with Session(self.engine) as session:
			if skip_debug:
				stmt = select(GroupAssignmentEvent.pseudonym).where(
					GroupAssignmentEvent.group == group
				)
			else:
				stmt = select(GroupAssignmentEvent.pseudonym).where(
					GroupAssignmentEvent.group == group and 
					GroupAssignmentEvent.isDebug == False  # noqa: E712
				)

			expected_pseudonyms: list[str] = list(session.scalars(stmt))
			valid_pseudonyms: list[str] = []

			for pseudonym in expected_pseudonyms:
				try:
					participant = self.read_participant(session, pseudonym)
					valid_pseudonyms.append(pseudonym)
					yield participant
				except LogValidationError as e:
					lineInfo = (f'#{e.event.id}' if e.event is not None else '')
					logging.error(f'{getShortPseudo(pseudonym)}{lineInfo} is invalid: "{e}"')
				except AssertionError as e:
					logging.error(f'Something went wrong while parsing {pseudonym}: "{e}"')

			logging.info(' ------------ ')
			logging.info(f'{len(valid_pseudonyms)} of {len(expected_pseudonyms)} player logs passed validation')

	
	def read_participant(self, session: Session, pseudonym: str) -> StatsParticipant:
		statsParticipant = StatsParticipant(pseudonym, self.is_debug(session, pseudonym))
		player = session.get_one(Participant, pseudonym)

		events = session.execute(
			statement=select(LogEvent).where(LogEvent.pseudonym == statsParticipant.pseudonym)
		).scalars()

		log_validator = LogEventValidator()
		state_validator = GameStateValidator()

		logging.info(f'Validating {getShortPseudo(pseudonym)}')
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


	@staticmethod
	def is_debug(session: Session, pseudonym: str):
		result = session.execute(
			select(func.count()).where(
				GroupAssignmentEvent.pseudonym == pseudonym and
				GroupAssignmentEvent.isDebug
			)
		).scalar_one()

		return result > 0


def main():

	parser = argparse.ArgumentParser(description="A script to aggregate the logfiles from the ReverSim game into a csv file.")
	parser.add_argument('-i', '--instance-path', help='', default=INSTANCE_FOLDER)
	parser.add_argument("-o", "--output", help="The filename of the output statistic csv file", default='statistics.csv')
	parser.add_argument("-s", "--skipScreenshots", help="Skip the screenshot validation", action="store_true")
	parser.add_argument("-d", "--allowDebug", help="Allow debug groups to end up in the output", action="store_true")
	parser.add_argument("-l", "--log", metavar='LEVEL', help="Specify the log level, must be one of DEBUG, INFO, WARNING, ERROR or CRITICAL", default="INFO")
	
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
		instanceFolder=INSTANCE_FOLDER
	)
	gameConfigLegacy.setGameConfig(gameConfig)
	

	# Load the Level Loader
	JsonLevelList.singleton = JsonLevelList.fromFile(instanceFolder=INSTANCE_FOLDER)

	# Open the Database
	database_path = os.path.join(INSTANCE_FOLDER, DATABASE_PATH)
	engine = (create_engine("sqlite:///" + database_path, echo=False)
		.execution_options(sqlite_readonly = True))

	statsGenerator = StatisticsGenerator(INSTANCE_FOLDER, gameConfig, JsonLevelList, engine)
	data = list(statsGenerator.read_group('cognitive_obfuscation'))
	

if __name__ == '__main__':
	main()
