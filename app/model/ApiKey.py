from datetime import datetime, timezone
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.database import db


class ApiKey(db.Model):
	token: Mapped[str] = mapped_column(primary_key=True)
	user: Mapped[str] = mapped_column(String(64))
	created: Mapped[datetime] = mapped_column(DateTime)

	def __init__(self, token: str, user: str) -> None:
		self.token = token
		self.user = user
		self.created = datetime.now(timezone.utc)
