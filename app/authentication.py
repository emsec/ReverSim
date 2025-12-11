import logging
import os
import secrets

from flask_httpauth import HTTPTokenAuth  # type: ignore

from app.config import BEARER_TOKEN_BYTES
from app.model.ApiKey import ApiKey
from app.storage.database import db
from app.utilsGame import safe_join

auth = HTTPTokenAuth(scheme='Bearer')

USER_METRICS = 'api_metrics'

@auth.verify_token # type: ignore
def verifyToken(token: str) -> ApiKey|None:
	"""Check if this token exists. If yes return the user object, otherwise return `None`

	https://flask-httpauth.readthedocs.io/en/latest/#flask_httpauth.HTTPTokenAuth.verify_token
	"""

	return db.session.query(ApiKey).filter_by(token=token).first()


def populate_data(instance_path: str):
	if ApiKey.query.count() < 1:
		apiKey = ApiKey(secrets.token_urlsafe(BEARER_TOKEN_BYTES), USER_METRICS)
		db.session.add(apiKey)
		db.session.commit()

	defaultToken = db.session.query(ApiKey).where(ApiKey.user == USER_METRICS).first()
	if defaultToken is not None:
		
		# Try to write the bearer secret to a file so other containers can use it
		try:
			folder = safe_join(instance_path, 'secrets')
			os.makedirs(folder, exist_ok=True)
			with open(safe_join(folder, 'bearer_api.txt'), encoding='UTF-8', mode='wt') as f:
				f.write(defaultToken.token)

		except Exception as e:
			# When the file can't be created print the bearer to stdout
			logging.error('Could not write bearer token to file: ' + str(e))
			logging.info('Bearer token for /metrics endpoint: ' + defaultToken.token)
