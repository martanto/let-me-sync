import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SERVER_DIR = BASE_DIR / "server"
DATA_ROOT = SERVER_DIR / "uploads"
DATABASE_URL = f"sqlite:///{SERVER_DIR / 'database' / 'data.db'}"

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
APP_ENV = os.getenv("APP_ENV", "development")

_server_url = urlparse(os.getenv("SERVER_URL", "http://localhost:8000"))
SERVER_HOST = _server_url.hostname or "localhost"
SERVER_PORT = _server_url.port or 8000

DATA_TYPES = ["seismic", "deformation", "multigas", "visual", "weather", "paper"]

DATA_TYPE_ICONS = {
    "seismic": "activity",
    "deformation": "move",
    "multigas": "wind",
    "visual": "camera",
    "weather": "cloud",
    "paper": "file-text",
}

DATA_TYPE_LABELS = {
    "seismic": "Seismic",
    "deformation": "Deformation",
    "multigas": "Multigas",
    "visual": "Visual",
    "weather": "Weather",
    "paper": "Paper",
}

STATIONS = ["sta1", "sta2", "sta3", "sta4", "sta5"]
