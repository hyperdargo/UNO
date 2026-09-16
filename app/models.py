from datetime import UTC, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(db.Model, UserMixin):
    # Table name and columns match the original app so existing databases keep working.
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    stats = db.relationship("PlayerStats", uselist=False, back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class PlayerStats(db.Model):
    """Lifetime record. Ranked numbers only count games with two or more humans."""

    __tablename__ = "player_stats"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    games = db.Column(db.Integer, nullable=False, default=0)
    wins = db.Column(db.Integer, nullable=False, default=0)
    wins_normal = db.Column(db.Integer, nullable=False, default=0)
    wins_no_mercy = db.Column(db.Integer, nullable=False, default=0)
    points = db.Column(db.Integer, nullable=False, default=0)
    bot_games = db.Column(db.Integer, nullable=False, default=0)
    bot_wins = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    user = db.relationship("User", back_populates="stats")

    def to_dict(self) -> dict:
        return {
            "games": self.games,
            "wins": self.wins,
            "wins_normal": self.wins_normal,
            "wins_no_mercy": self.wins_no_mercy,
            "points": self.points,
            "bot_games": self.bot_games,
            "bot_wins": self.bot_wins,
        }


def stats_for(user: User) -> PlayerStats:
    if user.stats is None:
        user.stats = PlayerStats(games=0, wins=0, wins_normal=0, wins_no_mercy=0, points=0, bot_games=0, bot_wins=0)
    return user.stats
