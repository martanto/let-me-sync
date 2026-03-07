from datetime import datetime

import bcrypt
from fastapi import Form, Depends, Request, APIRouter, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from server.models import File, Role, User, ApiKey, Station, DataType
from server.utils.helpers import (
    slugify,
    generate_token,
    sha256_of_token,
    human_readable_size,
)
from server.database.connection import get_db


router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="server/templates")
templates.env.globals["now"] = datetime.now


# ── Users ──────────────────────────────────────────────────────────────────────


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    roles = db.query(Role).order_by(Role.id).all()
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "user": request.session.get("user"),
            "users": users,
            "roles": roles,
            "flash": flash,
        },
    )


@router.post("/users")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    role_obj = db.query(Role).filter(Role.code == role).first()
    if not role_obj:
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        request.session["flash"] = {
            "type": "error",
            "message": f"Username '{username}' already exists",
        }
        return RedirectResponse(url="/admin/users", status_code=302)
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = User(username=username, password_hash=pw_hash, roles=[role_obj])
    db.add(user)
    db.commit()
    request.session["flash"] = {
        "type": "success",
        "message": f"User '{username}' created",
    }
    return RedirectResponse(url="/admin/users", status_code=302)


@router.post("/users/{user_id}/change-password")
async def change_password(
    user_id: int,
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if new_password != confirm_password:
        request.session["flash"] = {
            "type": "error",
            "message": "Passwords do not match",
        }
        return RedirectResponse(url="/admin/users", status_code=302)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    db.commit()
    request.session["flash"] = {
        "type": "success",
        "message": f"Password updated for '{user.username}'",
    }
    return RedirectResponse(url="/admin/users", status_code=302)


@router.post("/users/{user_id}/delete")
async def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    current = request.session.get("user")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if current and current["id"] == user_id:
        request.session["flash"] = {
            "type": "error",
            "message": "Cannot delete your own account",
        }
        return RedirectResponse(url="/admin/users", status_code=302)
    db.delete(user)
    db.commit()
    request.session["flash"] = {
        "type": "success",
        "message": f"User '{user.username}' deleted",
    }
    return RedirectResponse(url="/admin/users", status_code=302)


# ── API Keys ───────────────────────────────────────────────────────────────────


@router.get("/api-keys", response_class=HTMLResponse)
async def api_keys_page(request: Request, db: Session = Depends(get_db)):
    keys = db.query(ApiKey).order_by(ApiKey.id).all()
    flash = request.session.pop("flash", None)
    new_key_flash = request.session.pop("new_key", None)
    return templates.TemplateResponse(
        "api_keys.html",
        {
            "request": request,
            "user": request.session.get("user"),
            "keys": keys,
            "flash": flash,
            "new_key": new_key_flash,
        },
    )


@router.post("/api-keys")
async def create_api_key(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(ApiKey).filter(ApiKey.name == name).first()
    if existing:
        request.session["flash"] = {
            "type": "error",
            "message": f"Key name '{name}' already exists",
        }
        return RedirectResponse(url="/admin/api-keys", status_code=302)
    token = generate_token()
    token_hash = sha256_of_token(token)
    current_user = request.session.get("user", {})
    key = ApiKey(
        name=name,
        key_hash=token_hash,
        created_by=current_user.get("username", "unknown"),
    )
    db.add(key)
    db.commit()
    request.session["new_key"] = {"name": name, "token": token}
    request.session["flash"] = {
        "type": "success",
        "message": f"API key '{name}' created — copy the token below",
    }
    return RedirectResponse(url="/admin/api-keys", status_code=302)


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(key_id: int, request: Request, db: Session = Depends(get_db)):
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    key.revoked = not key.revoked
    db.commit()
    status = "revoked" if key.revoked else "activated"
    request.session["flash"] = {
        "type": "success",
        "message": f"Key '{key.name}' {status}",
    }
    return RedirectResponse(url="/admin/api-keys", status_code=302)


@router.post("/api-keys/{key_id}/delete")
async def delete_api_key(key_id: int, request: Request, db: Session = Depends(get_db)):
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    name = key.name
    db.delete(key)
    db.commit()
    request.session["flash"] = {"type": "success", "message": f"Key '{name}' deleted"}
    return RedirectResponse(url="/admin/api-keys", status_code=302)


# ── Data Types ─────────────────────────────────────────────────────────────────


@router.get("/data-types", response_class=HTMLResponse)
async def data_types_page(request: Request, db: Session = Depends(get_db)):
    data_types = db.query(DataType).order_by(DataType.id).all()
    file_stats = {
        code: {"count": count, "size": size or 0}
        for code, count, size in db.query(
            File.type_code,
            func.count(File.id),
            func.sum(File.file_size),
        )
        .group_by(File.type_code)
        .all()
    }
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        "data_types.html",
        {
            "request": request,
            "user": request.session.get("user"),
            "data_types": data_types,
            "file_stats": file_stats,
            "human_readable_size": human_readable_size,
            "flash": flash,
        },
    )


@router.post("/data-types")
async def create_data_type(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    code = slugify(name)
    existing = db.query(DataType).filter(DataType.code == code).first()
    if existing:
        request.session["flash"] = {
            "type": "error",
            "message": f"Data type '{name}' already exists (code: {code})",
        }
        return RedirectResponse(url="/admin/data-types", status_code=302)
    db.add(DataType(name=name, code=code))
    db.commit()
    request.session["flash"] = {
        "type": "success",
        "message": f"Data type '{name}' created",
    }
    return RedirectResponse(url="/admin/data-types", status_code=302)


@router.post("/data-types/{dt_id}/delete")
async def delete_data_type(dt_id: int, request: Request, db: Session = Depends(get_db)):
    dt = db.query(DataType).filter(DataType.id == dt_id).first()
    if not dt:
        raise HTTPException(status_code=404, detail="Data type not found")
    name = dt.name
    try:
        db.delete(dt)
        db.commit()
        request.session["flash"] = {
            "type": "success",
            "message": f"Data type '{name}' deleted",
        }
    except IntegrityError:
        db.rollback()
        request.session["flash"] = {
            "type": "error",
            "message": f"Cannot delete '{name}': files are associated with it",
        }
    return RedirectResponse(url="/admin/data-types", status_code=302)


# ── Stations ───────────────────────────────────────────────────────────────────


@router.get("/stations", response_class=HTMLResponse)
async def stations_page(request: Request, db: Session = Depends(get_db)):
    stations = db.query(Station).order_by(Station.id).all()
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        "stations.html",
        {
            "request": request,
            "user": request.session.get("user"),
            "stations": stations,
            "flash": flash,
        },
    )


@router.post("/stations")
async def create_station(
    request: Request,
    name: str = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(Station).filter(Station.code == code).first()
    if existing:
        request.session["flash"] = {
            "type": "error",
            "message": f"Station code '{code}' already exists",
        }
        return RedirectResponse(url="/admin/stations", status_code=302)
    db.add(Station(name=name, code=code))
    db.commit()
    request.session["flash"] = {
        "type": "success",
        "message": f"Station '{name}' created",
    }
    return RedirectResponse(url="/admin/stations", status_code=302)


@router.post("/stations/{station_id}/delete")
async def delete_station(
    station_id: int, request: Request, db: Session = Depends(get_db)
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    name = station.name
    try:
        db.delete(station)
        db.commit()
        request.session["flash"] = {
            "type": "success",
            "message": f"Station '{name}' deleted",
        }
    except IntegrityError:
        db.rollback()
        request.session["flash"] = {
            "type": "error",
            "message": f"Cannot delete '{name}': files are associated with it",
        }
    return RedirectResponse(url="/admin/stations", status_code=302)
