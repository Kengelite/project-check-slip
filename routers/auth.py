import os
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from datetime import timedelta
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

from database import get_db
import models
from dependencies import get_current_user, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(tags=["Auth"])

# ==========================================
# 🟢 ตั้งค่า Google OAuth
# ==========================================
# ดึงค่าจาก .env
config = Config('.env')
oauth = OAuth(config)

oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# ==========================================
#  1. ระบบ Login ด้วย Email / Password ปกติ
# ==========================================
@router.post("/login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # เพิ่ม joinedload เพื่อดึงชื่อ Role ออกมาด้วย และเช็คว่า User ยังไม่ถูก Soft Delete
    result = await db.execute(
        select(models.User)
        .options(joinedload(models.User.role))
        .filter(models.User.email == form_data.username)
        .filter(models.User.is_deleted == False) 
    )
    user = result.scalars().first()
    
    # กรณีหาไม่เจอ, โดนลบไปแล้ว, หรือรหัสผ่านผิด
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง หรือบัญชีนี้ถูกระงับการใช้งาน")
        
    # สร้าง Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    
    # ดึงชื่อ Role ส่งกลับไปให้หน้าเว็บซ่อนเมนู
    role_name = user.role.name if user.role else ""

    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_role": role_name
    }

# ==========================================
#  2. ระบบ Sign in with Google
# ==========================================
@router.get("/auth/google/login")
async def login_via_google(request: Request):
    # วิ่งไปหน้าขอสิทธิ์ของ Google
    redirect_uri = str(request.url_for('auth_google_callback'))
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/auth/google/callback", name="auth_google_callback")
async def auth_google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        # รับ Token และข้อมูลจาก Google
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            raise HTTPException(status_code=400, detail="ไม่สามารถดึงข้อมูลจาก Google ได้")
    except Exception:
        # ถ้าพังให้เด้งกลับไปหน้า login พร้อมแจ้งเตือน
        return RedirectResponse(url="/login?error=google_auth_failed")

    email = user_info.get("email")

    # ค้นหา User ในระบบของเรา
    result = await db.execute(
        select(models.User).options(joinedload(models.User.role)).filter(models.User.email == email)
    )
    user = result.scalars().first()

    # 🔴 ถ้าไม่เคยมีบัญชีมาก่อนเลย -> เตะกลับไปหน้า Login และส่งพารามิเตอร์ error
    if not user:
        return RedirectResponse(url="/login?error=user_not_found")

    # ถ้าระงับบัญชีอยู่ ห้ามเข้า
    if getattr(user, 'is_deleted', False):
        return RedirectResponse(url="/login?error=account_suspended")

    # สร้าง JWT Token ของระบบเรา
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    role_name = user.role.name if user.role else ""

    # ส่ง Token กลับไปที่หน้า auth-success เพื่อรัน JavaScript ฝังลง LocalStorage
    redirect_url = f"/auth-success?token={access_token}&role={role_name}"
    return RedirectResponse(url=redirect_url)
# ==========================================
#  3. ออกจากระบบ และ ข้อมูลผู้ใช้งานปัจจุบัน
# ==========================================
@router.post("/logout")
async def logout(current_user: models.User = Depends(get_current_user)):
    # เนื่องจาก JWT เป็น Stateless การ logout จริงๆ จะไปทำฝั่ง Frontend (ลบ LocalStorage)
    return {"status": "success", "message": "ออกจากระบบสำเร็จ"}

@router.get("/me")
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": str(current_user.id), 
        "email": current_user.email, 
        "full_name": current_user.full_name
    }