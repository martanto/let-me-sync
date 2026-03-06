import sys
from contextlib import asynccontextmanager
from pathlib import Path
import bcrypt
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from server.config import SECRET_KEY, DEBUG, APP_ENV, DATA_ROOT, DATA_TYPES
from server.database.connection import engine, SessionLocal
from server.models import User, ApiKey, DataFile
from server.middleware import AuthMiddleware
from server.routes import auth, files, sync, admin
from server.utils.helpers import generate_token, sha256_of_token


def seed_dev_data(db):
    from datetime import datetime

    users_data = [
        ("admin", "admin123", "admin"),
        ("uploader", "uploader123", "uploader"),
        ("downloader", "downloader123", "downloader"),
    ]
    for username, password, role in users_data:
        if not db.query(User).filter(User.username == username).first():
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            db.add(User(username=username, password_hash=pw_hash, role=role))

    token = "dev-test-token-00000000000000000000000000000000"
    token_hash = sha256_of_token(token)
    if not db.query(ApiKey).filter(ApiKey.name == "dev-key").first():
        db.add(ApiKey(name="dev-key", key_hash=token_hash, created_by="admin"))
        print(f"\n[DEV] API Key token: Bearer {token}\n")

    from server.utils.helpers import get_sds_path, get_upload_path

    # Seismic dummy files using SDS layout: seismic/YEAR/NET/STA/CHAN.TYPE/NET.STA.LOC.CHAN.TYPE.YEAR.DAY
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

    # Non-seismic dummy files
    other_dummies = [
        ("deformation", "STA1", "2024", "gps_daily.csv"),
        ("multigas", "STA3", "2024", "so2_flux.csv"),
        ("visual", "STA1", "2024", "cam01_2024001.jpg"),
        ("weather", "STA2", "2024", "met_2024001.csv"),
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


def prompt_create_admin(db):
    print("\nNo users found. Create an admin account:")
    username = input("  Username: ").strip()
    password = input("  Password: ").strip()
    if not username or not password:
        print("Username and password cannot be empty. Exiting.")
        sys.exit(1)
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db.add(User(username=username, password_hash=pw_hash, role="admin"))
    db.commit()
    print(f"  Admin '{username}' created.\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    from server.models import User, ApiKey, DataFile  # ensure models are imported
    from server.database.connection import Base
    Base.metadata.create_all(bind=engine)

    # Ensure uploads directory exists
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        if DEBUG and APP_ENV != "production":
            seed_dev_data(db)
        else:
            if db.query(User).count() == 0:
                prompt_create_admin(db)
    finally:
        db.close()

    yield


app = FastAPI(title="Let Me Sync", lifespan=lifespan)

# Middleware is applied in reverse order: AuthMiddleware wraps first, SessionMiddleware outermost
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="lms_session")

app.mount("/static", StaticFiles(directory="server/static"), name="static")

app.include_router(auth.router)
app.include_router(files.router)
app.include_router(sync.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
