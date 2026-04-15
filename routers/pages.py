import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
router = APIRouter(tags=["Pages"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "frontend"))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

@router.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/login")
async def serve_login_html(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/dashboard")
async def serve_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@router.get("/users")
async def user_html(request: Request):
    return templates.TemplateResponse("users.html", {"request": request})

@router.get("/roles")
async def role_html(request: Request):
    return templates.TemplateResponse("roles.html", {"request": request})

@router.get("/passed")
async def passed_html(request: Request):
    return templates.TemplateResponse("passed.html", {"request": request})

@router.get("/failed")
async def failed_html(request: Request):
    return templates.TemplateResponse("failed.html", {"request": request})

@router.get("/auth-success")
async def auth_success_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "auth-success.html"))


@router.get("/key")
async def key_html(request: Request):
    return templates.TemplateResponse("key.html", {"request": request})