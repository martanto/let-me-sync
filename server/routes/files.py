import re
import asyncio
from datetime import date as date_type, datetime, timedelta

import zipstream
from fastapi import (
    File as FastAPIFile,
    Form,
    Query,
    Depends,
    Request,
    APIRouter,
    UploadFile,
    HTTPException,
)
from sqlalchemy.orm import Session
from fastapi.responses import (
    FileResponse as FileResponseFastAPI,
    HTMLResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates

from server.config import DATA_ROOT, DATA_TYPES, DATA_TYPE_ICONS, DATA_TYPE_LABELS
from server.models import File
from server.schemas import FileResponse
from server.utils.helpers import (
    CSV_DATA_TYPES,
    get_sds_path,
    sha256_of_file,
    get_upload_path,
    human_readable_size,
    validate_and_count_csv,
)
from server.database.connection import get_db


router = APIRouter()
templates = Jinja2Templates(directory="server/templates")
templates.env.globals["now"] = datetime.now


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")
    cards = []
    for dt in DATA_TYPES:
        count = db.query(File).filter(File.type_code == dt).count()
        cards.append(
            {
                "data_type": dt,
                "label": DATA_TYPE_LABELS[dt],
                "icon": DATA_TYPE_ICONS[dt],
                "count": count,
            }
        )
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "cards": cards,
            "flash": flash,
        },
    )


@router.get("/files/{data_type}", response_class=HTMLResponse)
async def files_page(
    request: Request,
    data_type: str,
    station: str = None,
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    if data_type not in DATA_TYPES:
        raise HTTPException(status_code=404, detail="Unknown data type")
    user = request.session.get("user")
    query = db.query(File).filter(File.type_code == data_type)
    if station:
        query = query.filter(File.station_code == station)
    query = query.order_by(File.uploaded_at.desc())
    total = query.count()
    page = max(1, page)
    if limit <= 0:
        files = query.all()
        total_pages = 1
        page = 1
    else:
        total_pages = max(1, (total + limit - 1) // limit)
        page = min(page, total_pages)
        files = query.offset((page - 1) * limit).limit(limit).all()
    stations_in_db = [
        r[0]
        for r in db.query(File.station_code)
        .filter(File.type_code == data_type)
        .distinct()
        .all()
    ]
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        "files.html",
        {
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
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
        },
    )


@router.get("/files", response_model=list[FileResponse])
async def list_files_api(
    data_type: str = None,
    station: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(File)
    if data_type:
        query = query.filter(File.type_code == data_type)
    if station:
        query = query.filter(File.station_code == station)
    return query.all()


@router.get("/download/{file_id}")
async def download_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    record = db.query(File).filter(File.id == file_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    full_path = DATA_ROOT / record.file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponseFastAPI(path=str(full_path), filename=record.filename)


@router.get("/download-zip")
async def download_zip(ids: list[int] = Query(...), db: Session = Depends(get_db)):
    records = db.query(File).filter(File.id.in_(ids)).all()
    valid = [
        (r, DATA_ROOT / r.file_path)
        for r in records
        if (DATA_ROOT / r.file_path).exists()
    ]
    if not valid:
        raise HTTPException(status_code=404, detail="No files found")

    def iter_zip():
        zs = zipstream.ZipStream(compress_type=zipstream.ZIP_DEFLATED)
        for record, full_path in valid:
            zs.add_path(full_path, arcname=record.file_path)
        yield from zs

    async def async_generator():
        loop = asyncio.get_event_loop()
        gen = iter_zip()
        while True:
            chunk = await loop.run_in_executor(None, next, gen, None)
            if chunk is None:
                break
            yield chunk

    return StreamingResponse(
        async_generator(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=files.zip"},
    )


@router.post("/files/{file_id}/delete")
async def delete_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user or "admin" not in user.get("roles", []):
        raise HTTPException(status_code=403, detail="Admin only")
    record = db.query(File).filter(File.id == file_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    full_path = DATA_ROOT / record.file_path
    if full_path.exists():
        full_path.unlink()
    type_code = record.type_code
    db.delete(record)
    db.commit()
    request.session["flash"] = {
        "type": "success",
        "message": "File deleted successfully",
    }
    return RedirectResponse(url=f"/files/{type_code}", status_code=302)


@router.post("/upload")
async def upload_file(
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
    rel_path = str(dest.relative_to(DATA_ROOT))

    total_rows = None
    if data_type in CSV_DATA_TYPES:
        try:
            total_rows = validate_and_count_csv(str(dest))
        except Exception as e:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Invalid CSV: {e}")

    existing = db.query(File).filter(File.file_path == rel_path).first()
    if existing:
        existing.file_sha256 = file_hash
        existing.file_size = file_size
        existing.total_rows = total_rows
        existing.date = file_date
        existing.uploaded_at = datetime.utcnow()
        db.commit()
        return {"status": "updated", "id": existing.id}
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
        return {"status": "created", "id": record.id}
