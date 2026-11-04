"""Copy photos saved on disk (data/media) into the database for reports made before
files were stored there.

    uv run python -m app.media_to_db

Safe to run more than once: media that already has its file in the database is skipped. The
files on disk are left in place.
"""

from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import Media, MediaFile


def main() -> None:
    init_db()
    copied = missing = 0
    with SessionLocal() as db:
        pending = db.scalars(select(Media).where(~Media.file.has()).order_by(Media.id)).all()
        for media in pending:
            if media.path and Path(media.path).is_file():
                media.file = MediaFile.from_bytes(Path(media.path).read_bytes())
                copied += 1
            else:
                missing += 1
                print(f"media {media.id} (report {media.report_id}): no file at {media.path}")
        db.commit()
    print(f"copied {copied} file(s) into the database; {missing} without a file on disk")


if __name__ == "__main__":
    main()
