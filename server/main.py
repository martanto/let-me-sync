import subprocess
import sys
from contextlib import asynccontextmanager

import bcrypt
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from server.cli.seed import _seed_roles, seed
from server.config import SECRET_KEY, DEBUG, APP_ENV, DATA_ROOT
from server.database.connection import SessionLocal, check_db_connection
from server.models import Role, User
from server.middleware import AuthMiddleware
from server.routes import auth, files, sync, admin


def prompt_create_admin(db):
    print("\nNo users found. Create an admin account:")
    username = input("  Username: ").strip()
    password = input("  Password: ").strip()
    if not username or not password:
        print("Username and password cannot be empty. Exiting.")
        sys.exit(1)
    _seed_roles(db)
    role_obj = db.query(Role).filter(Role.code == "admin").first()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db.add(User(username=username, password_hash=pw_hash, roles=[role_obj]))
    db.commit()
    print(f"  Admin '{username}' created.\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        check_db_connection()
    except RuntimeError as exc:
        print(f"\n[ERROR] {exc}")
        sys.exit(1)

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

    # Ensure uploads directory exists
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        if DEBUG and APP_ENV != "production":
            seed(db)
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
