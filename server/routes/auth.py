from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import bcrypt
from server.database.connection import get_db
from server.models import User

router = APIRouter()
templates = Jinja2Templates(directory="server/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/", status_code=302)
    error = request.session.pop("flash_error", None)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        request.session["user"] = {"id": user.id, "username": user.username, "role": user.role}
        return RedirectResponse(url="/", status_code=302)
    request.session["flash_error"] = "Invalid username or password"
    return RedirectResponse(url="/login", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
