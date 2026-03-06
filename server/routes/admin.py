from datetime import datetime
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import bcrypt
from server.database.connection import get_db
from server.models import User, ApiKey
from server.utils.helpers import generate_token, sha256_of_token

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="server/templates")
templates.env.globals["now"] = datetime.now


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse("users.html", {
        "request": request,
        "user": request.session.get("user"),
        "users": users,
        "flash": flash,
    })


@router.post("/users")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    if role not in ("admin", "uploader", "downloader"):
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        request.session["flash"] = {"type": "error", "message": f"Username '{username}' already exists"}
        return RedirectResponse(url="/admin/users", status_code=302)
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = User(username=username, password_hash=pw_hash, role=role)
    db.add(user)
    db.commit()
    request.session["flash"] = {"type": "success", "message": f"User '{username}' created"}
    return RedirectResponse(url="/admin/users", status_code=302)


@router.post("/users/{user_id}/change-password")
async def change_password(
    user_id: int,
    request: Request,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    db.commit()
    request.session["flash"] = {"type": "success", "message": f"Password updated for '{user.username}'"}
    return RedirectResponse(url="/admin/users", status_code=302)


@router.post("/users/{user_id}/delete")
async def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    current = request.session.get("user")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if current and current["id"] == user_id:
        request.session["flash"] = {"type": "error", "message": "Cannot delete your own account"}
        return RedirectResponse(url="/admin/users", status_code=302)
    db.delete(user)
    db.commit()
    request.session["flash"] = {"type": "success", "message": f"User '{user.username}' deleted"}
    return RedirectResponse(url="/admin/users", status_code=302)


# ── API Keys ───────────────────────────────────────────────────────────────────

@router.get("/api-keys", response_class=HTMLResponse)
async def api_keys_page(request: Request, db: Session = Depends(get_db)):
    keys = db.query(ApiKey).order_by(ApiKey.id).all()
    flash = request.session.pop("flash", None)
    new_key_flash = request.session.pop("new_key", None)
    return templates.TemplateResponse("api_keys.html", {
        "request": request,
        "user": request.session.get("user"),
        "keys": keys,
        "flash": flash,
        "new_key": new_key_flash,
    })


@router.post("/api-keys")
async def create_api_key(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(ApiKey).filter(ApiKey.name == name).first()
    if existing:
        request.session["flash"] = {"type": "error", "message": f"Key name '{name}' already exists"}
        return RedirectResponse(url="/admin/api-keys", status_code=302)
    token = generate_token()
    token_hash = sha256_of_token(token)
    current_user = request.session.get("user", {})
    key = ApiKey(name=name, key_hash=token_hash, created_by=current_user.get("username", "unknown"))
    db.add(key)
    db.commit()
    request.session["new_key"] = {"name": name, "token": token}
    request.session["flash"] = {"type": "success", "message": f"API key '{name}' created — copy the token below"}
    return RedirectResponse(url="/admin/api-keys", status_code=302)


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(key_id: int, request: Request, db: Session = Depends(get_db)):
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    key.revoked = not key.revoked
    db.commit()
    status = "revoked" if key.revoked else "activated"
    request.session["flash"] = {"type": "success", "message": f"Key '{key.name}' {status}"}
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
