import sys
from contextlib import asynccontextmanager

import bcrypt
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from server.cli.seed import seed
from server.config import SECRET_KEY, DEBUG, APP_ENV, DATA_ROOT
from server.database.connection import Base, engine, SessionLocal
from server.models import User
from server.middleware import AuthMiddleware
from server.routes import auth, files, sync, admin


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
    Base.metadata.create_all(bind=engine)

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
