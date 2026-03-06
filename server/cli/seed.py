"""
Seed script for development/demo purposes.
Creates dummy files for all data types and stations, and seeds default users and API key.

Only runs when DEBUG=true and APP_ENV != production in .env.

Usage:
    uv run server:seed
"""

import random
from datetime import date, datetime, timedelta, timezone

import bcrypt

from server.config import APP_ENV, DATA_ROOT, DEBUG, STATIONS
from server.database.connection import Base, SessionLocal, engine
from server.models import ApiKey, DataFile, User
from server.utils.helpers import (
    get_sds_path,
    get_upload_path,
    sha256_of_file,
    sha256_of_token,
)

_CSV_HEADERS = {
    "weather": "timestamp,temperature,humidity,wind_speed,wind_direction,rainfall,pressure\n",
    "deformation": "timestamp,east_mm,north_mm,up_mm,baseline_m\n",
    "multigas": "timestamp,so2_ppm,co2_ppm,h2s_ppm,co_ppm\n",
}

_NUM_CSV_DAYS = 30


def _generate_weather_row(ts: str) -> str:
    return (
        f"{ts},{round(random.uniform(20.0, 35.0), 2)},"
        f"{round(random.uniform(40.0, 95.0), 2)},"
        f"{round(random.uniform(0.0, 15.0), 2)},"
        f"{random.randint(0, 359)},"
        f"{round(random.uniform(0.0, 5.0), 2)},"
        f"{round(random.uniform(990.0, 1020.0), 2)}\n"
    )


def _generate_deformation_row(ts: str) -> str:
    return (
        f"{ts},{round(random.uniform(-5.0, 5.0), 3)},"
        f"{round(random.uniform(-5.0, 5.0), 3)},"
        f"{round(random.uniform(-3.0, 3.0), 3)},"
        f"{round(random.uniform(1000.0, 5000.0), 2)}\n"
    )


def _generate_multigas_row(ts: str) -> str:
    return (
        f"{ts},{round(random.uniform(0.0, 10.0), 3)},"
        f"{round(random.uniform(300.0, 800.0), 2)},"
        f"{round(random.uniform(0.0, 2.0), 3)},"
        f"{round(random.uniform(0.0, 1.0), 3)}\n"
    )


_ROW_GENERATORS = {
    "weather": _generate_weather_row,
    "deformation": _generate_deformation_row,
    "multigas": _generate_multigas_row,
}


def _generate_csv_content(data_type: str, target_date: date) -> str:
    lines = [_CSV_HEADERS[data_type]]
    row_count = random.randint(20, 24)
    gen = _ROW_GENERATORS[data_type]
    for hour in range(row_count):
        ts = f"{target_date}T{hour:02d}:00:00"
        lines.append(gen(ts))
    return "".join(lines)


def _seed_users(db) -> None:
    users_data = [
        ("admin", "admin123", "admin"),
        ("uploader", "uploader123", "uploader"),
        ("downloader", "downloader123", "downloader"),
    ]
    for username, password, role in users_data:
        if not db.query(User).filter(User.username == username).first():
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            db.add(User(username=username, password_hash=pw_hash, role=role))
    db.commit()


def _seed_api_key(db) -> None:
    token = "dev-test-token-00000000000000000000000000000000"
    token_hash = sha256_of_token(token)
    if not db.query(ApiKey).filter(ApiKey.name == "dev-key").first():
        db.add(ApiKey(name="dev-key", key_hash=token_hash, created_by="admin"))
        db.commit()
        print(f"\n[DEV] API Key token: Bearer {token}\n")


def _seed_seismic(db) -> None:
    seismic_dummies = [
        ("VG", "STA1", "", "EHZ", "D", "2024", "001"),
        ("VG", "STA2", "", "EHZ", "D", "2024", "002"),
    ]
    for net, sta, loc, chan, sds_type, year, day in seismic_dummies:
        dest = get_sds_path(DATA_ROOT, net, sta, loc, chan, sds_type, year, day)
        rel_path = str(dest.relative_to(DATA_ROOT)).replace("\\", "/")
        if not db.query(DataFile).filter(DataFile.file_path == rel_path).first():
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_text("dummy seismic data")
            db.add(DataFile(
                data_type="seismic",
                station=sta,
                filename=dest.name,
                file_path=rel_path,
                file_sha256="0" * 64,
                file_size=18,
                uploaded_at=datetime.utcnow(),
            ))
    db.commit()


def _seed_other(db) -> None:
    other_dummies = [
        ("visual", "STA1", "2024", "cam01_2024001.jpg"),
        ("paper", "STA1", "2024", "research_2024.pdf"),
    ]
    for data_type, station, year, filename in other_dummies:
        dest = get_upload_path(DATA_ROOT, data_type, station, year, filename)
        rel_path = str(dest.relative_to(DATA_ROOT)).replace("\\", "/")
        if not db.query(DataFile).filter(DataFile.file_path == rel_path).first():
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_text("dummy data")
            db.add(DataFile(
                data_type=data_type,
                station=station,
                filename=filename,
                file_path=rel_path,
                file_sha256="0" * 64,
                file_size=10,
                uploaded_at=datetime.utcnow(),
            ))
    db.commit()


def _seed_csv_files(db) -> None:
    today = date.today()
    created = 0
    for data_type in ("weather", "deformation", "multigas"):
        for station in STATIONS:
            for i in range(_NUM_CSV_DAYS):
                target_date = today - timedelta(days=_NUM_CSV_DAYS - i)
                year = str(target_date.year)
                filename = f"{target_date}.csv"
                dest = get_upload_path(DATA_ROOT, data_type, station.upper(), year, filename)
                rel_path = str(dest.relative_to(DATA_ROOT)).replace("\\", "/")
                if db.query(DataFile).filter(DataFile.file_path == rel_path).first():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                content = _generate_csv_content(data_type, target_date)
                dest.write_text(content, encoding="utf-8")
                sha = sha256_of_file(dest)
                size = dest.stat().st_size
                row_count = content.count("\n") - 1  # subtract header
                db.add(DataFile(
                    data_type=data_type,
                    station=station.upper(),
                    filename=filename,
                    file_path=rel_path,
                    file_sha256=sha,
                    file_size=size,
                    total_rows=row_count,
                    uploaded_at=datetime.now(timezone.utc) - timedelta(days=_NUM_CSV_DAYS - i),
                ))
                created += 1
    db.commit()
    print(f"[DEV] CSV seed: {created} files created for weather, deformation, multigas.")


def seed(db=None) -> None:
    Base.metadata.create_all(bind=engine)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        _seed_users(db)
        _seed_api_key(db)
        _seed_seismic(db)
        _seed_other(db)
        _seed_csv_files(db)
        print("[DEV] Seed complete.")
    finally:
        if own_db:
            db.close()


if __name__ == "__main__":
    if not DEBUG:
        print("Seeding is disabled. Set DEBUG=true in .env to enable.")
        raise SystemExit(0)
    if APP_ENV == "production":
        print("Seeding is not allowed when APP_ENV=production.")
        raise SystemExit(0)
    seed()
