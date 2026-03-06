import os
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from server.database.connection import get_db
from server.models import DataFile
from server.config import DATA_ROOT, DATA_TYPES, DATA_TYPE_ICONS, DATA_TYPE_LABELS, STATIONS
from server.utils.helpers import sha256_of_file, get_upload_path, get_sds_path, human_readable_size

router = APIRouter()
templates = Jinja2Templates(directory="server/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")
    cards = []
    for dt in DATA_TYPES:
        count = db.query(DataFile).filter(DataFile.data_type == dt).count()
        cards.append({
            "data_type": dt,
            "label": DATA_TYPE_LABELS[dt],
            "icon": DATA_TYPE_ICONS[dt],
            "count": count,
        })
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "cards": cards,
        "flash": flash,
    })


@router.get("/files/{data_type}", response_class=HTMLResponse)
async def files_page(request: Request, data_type: str, station: str = None, db: Session = Depends(get_db)):
    if data_type not in DATA_TYPES:
        raise HTTPException(status_code=404, detail="Unknown data type")
    user = request.session.get("user")
    query = db.query(DataFile).filter(DataFile.data_type == data_type)
    if station:
        query = query.filter(DataFile.station == station)
    files = query.order_by(DataFile.uploaded_at.desc()).all()
    stations_in_db = [
        r[0] for r in db.query(DataFile.station).filter(DataFile.data_type == data_type).distinct().all()
    ]
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse("files.html", {
        "request": request,
        "user": user,
        "data_type": data_type,
        "label": DATA_TYPE_LABELS[data_type],
        "icon": DATA_TYPE_ICONS[data_type],
        "files": files,
        "stations": stations_in_db,
        "selected_station": station,
        "human_readable_size": human_readable_size,
        "flash": flash,
    })


@router.get("/files", response_class=JSONResponse)
async def list_files_api(
    data_type: str = None,
    station: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(DataFile)
    if data_type:
        query = query.filter(DataFile.data_type == data_type)
    if station:
        query = query.filter(DataFile.station == station)
    files = query.all()
    return [
        {
            "id": f.id,
            "data_type": f.data_type,
            "station": f.station,
            "filename": f.filename,
            "file_path": f.file_path,
            "file_sha256": f.file_sha256,
            "file_size": f.file_size,
            "uploaded_at": f.uploaded_at.isoformat(),
        }
        for f in files
    ]


@router.get("/download/{file_id}")
async def download_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    record = db.query(DataFile).filter(DataFile.id == file_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    full_path = DATA_ROOT / record.file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path=str(full_path), filename=record.filename)


@router.post("/files/{file_id}/delete")
async def delete_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    record = db.query(DataFile).filter(DataFile.id == file_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    full_path = DATA_ROOT / record.file_path
    if full_path.exists():
        full_path.unlink()
    data_type = record.data_type
    db.delete(record)
    db.commit()
    request.session["flash"] = {"type": "success", "message": "File deleted successfully"}
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/files/{data_type}", status_code=302)


@router.post("/upload")
async def upload_file(
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
    rel_path = str(dest.relative_to(DATA_ROOT))

    existing = db.query(DataFile).filter(DataFile.file_path == rel_path).first()
    if existing:
        existing.file_sha256 = file_hash
        existing.file_size = file_size
        existing.uploaded_at = datetime.utcnow()
        db.commit()
        return {"status": "updated", "id": existing.id}
    else:
        record = DataFile(
            data_type=data_type,
            station=station,
            filename=file.filename,
            file_path=rel_path,
            file_sha256=file_hash,
            file_size=file_size,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"status": "created", "id": record.id}
