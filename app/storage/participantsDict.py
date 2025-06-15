import hashlib
import logging
import secrets
from datetime import datetime

from sqlalchemy.exc import NoResultFound

import app.config as gameConfig
from app.model.GroupStats import GroupStats
from app.model.Participant import Participant
from app.storage.database import db
from app.model.LogEvents import GameOverEvent
from app.utilsGame import EventType, now


def insertParticipant(participant: Participant):
	"""Store the participant in the participantsDict. Assumes a Flask App context is active!"""
	db.session.add(participant)
	db.session.commit()


def existsInMemory(pseudonym: str) -> bool:
	"""Right now, the participants are stored in memory, so after an application restart this will return false for participants which started their 
	session in the previous run."""
	return exists(pseudonym)


def exists(pseudonym: str) -> bool:
	"""Check if an entry for this participant exists.	
	"""
	return db.session.get(Participant, pseudonym) is not None


def get(pseudonym: str) -> Participant:
	"""Find the participant by pseudonym/ui

	Right now, the participants are stored in memory, therefore all participants are lost after a restart and will not be returned by this method.

	Raises a ValueError, if the participant does not exist. Also see the participantsDict.exist()
	"""
	try:
		return db.session.get_one(Participant, pseudonym)
	except NoResultFound:
		raise ValueError("No participant with pseudonym/ui \"" + pseudonym + "\"found.")


def getAutomaticGroup() -> str:
	"""Automatically assign the player to the group with the lowest number of finished players"""
	return GroupStats.getAutomaticGroup()


def increaseGroupCounter(participant: Participant, timeStamp: str) -> None:
	"""Called when the postSurvey Button is clicked"""
	if participant.group is None: # type: ignore
		raise RuntimeError("Invalid state: The group is still None")
	group = participant.group

	if not participant.startedPostsurvey and participant.isLastPhase():
		GroupStats.increasePlayersPostSurvey(group, participant.isDebug)
		logging.info(f'PostSurvey incremented {group}: {GroupStats.getPlayerCountPostSurvey(group)}')
	
	participant.logger.writeToLog(EventType.GameOver, '', timeStamp)

	event = GameOverEvent(
		clientTime=None, 
		serverTime=int(timeStamp),
		pseudonym=participant.pseudonym
	)
	event.commit()


def generatePseudonym(srcIP: str) -> str:
	inputHash = datetime.now().strftime("%H:%M:%S") + srcIP + secrets.token_hex(128)
	return hashlib.blake2b(inputHash.encode(), digest_size=int(gameConfig.PSEUDONYM_LENGTH/2)).hexdigest()


def getConnectedPlayers() -> int:
	"""Get the number of players currently connected
	
	Count all players, that reached out to the /testConnection endpoint within the last 
	`BACK_ONLINE_THRESHOLD_S` seconds (5 seconds).
	"""
	# All lastConnection timestamps greater than this are considered connected
	lastConsideredOnline = now() - gameConfig.BACK_ONLINE_THRESHOLD_S*1000 # [ms]

	playersConnected = (db.session.query(Participant)
		.filter(Participant.lastConnection > lastConsideredOnline)
		.count()
	)

	return playersConnected
