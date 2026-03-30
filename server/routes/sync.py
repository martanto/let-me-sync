import re
from datetime import date as date_type, datetime, timedelta

from fastapi import (
    File as FastAPIFile,
    Form,
    Depends,
    Request,
    APIRouter,
    UploadFile,
    HTTPException,
)
from sqlalchemy.orm import Session

from server.config import DATA_ROOT, DATA_TYPES
from server.models import File
from server.schemas import SyncCheckItem, SyncCheckResponse
from server.utils.helpers import (
    CSV_DATA_TYPES,
    get_sds_path,
    sha256_of_file,
    get_upload_path,
    validate_and_count_csv,
)
from server.database.connection import get_db


router = APIRouter(prefix="/sync")


@router.post("/check", response_model=SyncCheckResponse)
async def sync_check(items: list[SyncCheckItem], db: Session = Depends(get_db)):
    to_upload = []
    for item in items:
        if item.data_type not in DATA_TYPES:
            continue
        records = (
            db.query(File)
            .filter(
                File.type_code == item.data_type,
                File.station_code == item.station,
                File.filename == item.filename,
            )
            .all()
        )
        if not records:
            to_upload.append(item)
        else:
            if not any(r.file_sha256 == item.sha256 for r in records):
                to_upload.append(item)

    return {"to_upload": [i.model_dump() for i in to_upload]}


@router.post("/upload")
async def sync_upload(
    request: Request,
    file: UploadFile = FastAPIFile(...),
    data_type: str = Form(...),
    station: str = Form(...),
    date: str = Form(None),
    # SDS fields (required when data_type == "seismic")
    net: str = Form(None),
    loc: str = Form(""),  # location code is optional in SDS (can be empty)
    chan: str = Form(None),
    sds_type: str = Form(None),
    day: str = Form(None),
    db: Session = Depends(get_db),
):
    if data_type not in DATA_TYPES:
        raise HTTPException(status_code=400, detail="Invalid data_type")

    if data_type in CSV_DATA_TYPES:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.csv", file.filename):
            raise HTTPException(
                status_code=400, detail="Filename must match YYYY-MM-DD.csv"
            )

    if data_type == "seismic":
        if not all(x is not None for x in [net, chan, sds_type, day]):
            raise HTTPException(
                status_code=400,
                detail="Seismic uploads require: net, loc, chan, sds_type, day",
            )
        year = (
            file.filename.split(".")[-2]
            if len(file.filename.split(".")) >= 7
            else str(datetime.utcnow().year)
        )
        dest = get_sds_path(DATA_ROOT, net, station, loc, chan, sds_type, year, day)
        file_date = date_type(int(year), 1, 1) + timedelta(days=int(day) - 1)
    else:
        year = str(datetime.utcnow().year)
        dest = get_upload_path(DATA_ROOT, data_type, station, year, file.filename)
        if data_type in CSV_DATA_TYPES:
            file_date = date_type.fromisoformat(file.filename[:-4])
        else:
            file_date = date_type.fromisoformat(date) if date else None
    dest.parent.mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    dest.write_bytes(contents)

    file_hash = sha256_of_file(dest)
    file_size = dest.stat().st_size
    rel_path = str(dest.relative_to(DATA_ROOT)).replace("\\", "/")

    total_rows = None
    if data_type in CSV_DATA_TYPES:
        try:
            total_rows = validate_and_count_csv(str(dest))
        except Exception as e:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Invalid CSV: {e}")

    existing = (
        db.query(File)
        .filter(
            File.type_code == data_type,
            File.station_code == station,
            File.filename == file.filename,
        )
        .first()
    )

    if existing:
        existing.file_sha256 = file_hash
        existing.file_size = file_size
        existing.file_path = rel_path
        existing.total_rows = total_rows
        existing.date = file_date
        existing.uploaded_at = datetime.utcnow()
        db.commit()
        return {"status": "updated", "id": existing.id, "sha256": file_hash}
    else:
        record = File(
            type_code=data_type,
            station_code=station,
            filename=file.filename,
            file_path=rel_path,
            file_sha256=file_hash,
            file_size=file_size,
            total_rows=total_rows,
            date=file_date,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"status": "created", "id": record.id, "sha256": file_hash}
