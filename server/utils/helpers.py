import re
import csv
import hashlib
import secrets
from pathlib import Path


def sha256_of_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sha256_of_file(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def get_upload_path(
    data_root: Path, data_type: str, station: str, year: str, filename: str
) -> Path:
    return data_root / data_type / station / year / filename


def get_sds_path(
    data_root: Path,
    net: str,
    sta: str,
    loc: str,
    chan: str,
    sds_type: str,
    year: str,
    day: str,
) -> Path:
    """Return the full path for a seismic file following SDS layout:
    seismic/YEAR/NET/STA/CHAN.TYPE/NET.STA.LOC.CHAN.TYPE.YEAR.DAY
    """
    filename = f"{net}.{sta}.{loc}.{chan}.{sds_type}.{year}.{day}"
    return data_root / "seismic" / year / net / sta / f"{chan}.{sds_type}" / filename


CSV_DATA_TYPES = {"weather", "deformation"}


def validate_and_count_csv(file_path: str) -> int:
    count = 0
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for _ in reader:
            count += 1
    return count


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value)
    return re.sub(r"^-+|-+$", "", value)


def human_readable_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
