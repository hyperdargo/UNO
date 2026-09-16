"""Import scores from the original encrypted score file into the database.

The first version of this app kept wins and points in `scores.enc.txt`, encrypted
with a Fernet key in `score_key.key`. Run this once to carry those numbers over:

    pip install cryptography
    python scripts/import_legacy_scores.py --scores legacy/scores.enc.txt --key legacy/score_key.key

Existing players are updated; unknown usernames are reported and skipped.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User, stats_for  # noqa: E402


def load(scores_path: Path, key_path: Path) -> dict:
    from cryptography.fernet import Fernet

    fernet = Fernet(key_path.read_bytes())
    return json.loads(fernet.decrypt(scores_path.read_bytes()).decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, default=Path("legacy/scores.enc.txt"))
    parser.add_argument("--key", type=Path, default=Path("legacy/score_key.key"))
    parser.add_argument("--dry-run", action="store_true", help="show what would change and stop")
    args = parser.parse_args()

    if not args.scores.exists() or not args.key.exists():
        print(f"Nothing to import: {args.scores} or {args.key} is missing.")
        return 1

    data = load(args.scores, args.key)
    app = create_app()
    imported, missing = 0, []
    with app.app_context():
        for username, record in data.items():
            user = User.query.filter_by(username=username).first()
            if not user:
                missing.append(username)
                continue
            stats = stats_for(user)
            stats.wins = max(stats.wins, int(record.get("wins", 0)))
            stats.points = max(stats.points, int(record.get("points", 0)))
            stats.games = max(stats.games, stats.wins)
            imported += 1
        if args.dry_run:
            db.session.rollback()
            print(f"Dry run: {imported} player(s) would be updated.")
        else:
            db.session.commit()
            print(f"Imported scores for {imported} player(s).")
    if missing:
        print(f"No account found for: {', '.join(sorted(missing))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
