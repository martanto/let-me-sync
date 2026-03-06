import re
from datetime import datetime
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from server.database.connection import get_db
from server.models import DataFile
from server.config import DATA_ROOT, DATA_TYPES
from server.schemas import SyncCheckItem
from server.utils.helpers import sha256_of_file, get_upload_path, get_sds_path, validate_and_count_csv, CSV_DATA_TYPES

router = APIRouter(prefix="/sync")


@router.post("/check")
async def sync_check(items: list[SyncCheckItem], db: Session = Depends(get_db)):
    to_upload = []
    for item in items:
        if item.data_type not in DATA_TYPES:
            continue
        # Find by data_type + station + filename
        records = (
            db.query(DataFile)
            .filter(
                DataFile.data_type == item.data_type,
                DataFile.station == item.station,
                DataFile.filename == item.filename,
            )
            .all()
        )
        if not records:
            to_upload.append(item)
        else:
            # Check if any record has matching hash
            if not any(r.file_sha256 == item.sha256 for r in records):
                to_upload.append(item)

    return {"to_upload": [i.model_dump() for i in to_upload]}


@router.post("/upload")
async def sync_upload(
    request: Request,
    file: UploadFile = File(...),
    data_type: str = Form(...),
    station: str = Form(...),
    # SDS fields (required when data_type == "seismic")
    net: str = Form(None),
    loc: str = Form(""),   # location code is optional in SDS (can be empty)
    chan: str = Form(None),
    sds_type: str = Form(None),
    day: str = Form(None),
    db: Session = Depends(get_db),
):
    if data_type not in DATA_TYPES:
        raise HTTPException(status_code=400, detail="Invalid data_type")

    if data_type in CSV_DATA_TYPES:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.csv", file.filename):
            raise HTTPException(status_code=400, detail="Filename must match YYYY-MM-DD.csv")

    if data_type == "seismic":
        if not all(x is not None for x in [net, chan, sds_type, day]):
            raise HTTPException(
                status_code=400,
                detail="Seismic uploads require: net, loc, chan, sds_type, day",
            )
        year = file.filename.split(".")[-2] if len(file.filename.split(".")) >= 7 else str(datetime.utcnow().year)
        dest = get_sds_path(DATA_ROOT, net, station, loc, chan, sds_type, year, day)
    else:
        year = str(datetime.utcnow().year)
        dest = get_upload_path(DATA_ROOT, data_type, station, year, file.filename)
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
        db.query(DataFile)
        .filter(
            DataFile.data_type == data_type,
            DataFile.station == station,
            DataFile.filename == file.filename,
        )
        .first()
    )

    if existing:
        existing.file_sha256 = file_hash
        existing.file_size = file_size
        existing.file_path = rel_path
        existing.total_rows = total_rows
        existing.uploaded_at = datetime.utcnow()
        db.commit()
        return {"status": "updated", "id": existing.id, "sha256": file_hash}
    else:
        record = DataFile(
            data_type=data_type,
            station=station,
            filename=file.filename,
            file_path=rel_path,
            file_sha256=file_hash,
            file_size=file_size,
            total_rows=total_rows,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"status": "created", "id": record.id, "sha256": file_hash}
