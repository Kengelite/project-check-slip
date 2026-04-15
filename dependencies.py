import os
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader # นำเข้า APIKeyHeader เพิ่มเติม
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
import models

load_dotenv()

# ==========================================
#  ตั้งค่าพื้นฐาน (JWT & API Key)
# ==========================================
SECRET_KEY = os.getenv("SECRET_KEY", "fallback_secret_key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Schema สำหรับ JWT (รับผ่าน Authorization: Bearer ...)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

# Schema สำหรับ API Key (รับผ่าน Header ชื่อ X-API-Key)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


# ==========================================
#  ฟังก์ชันเข้ารหัสและตรวจสอบรหัสผ่าน
# ==========================================
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ==========================================
#  วิธีที่ 1: ตรวจสอบด้วย JWT Token (ใช้สำหรับหน้าเว็บระบบหลังบ้าน)
# ==========================================
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    result = await db.execute(select(models.User).filter(models.User.email == email))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return user


# ==========================================
#  วิธีที่ 2: ตรวจสอบด้วย API Key (ใช้สำหรับเครื่องอื่น หรือระบบภายนอกยิงเข้ามาเช็คสลิป)
# ==========================================
async def verify_api_key(
    api_key: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db)
):
    # 1. ค้นหา Token ในตาราง APIToken
    result = await db.execute(
        select(models.APIToken).filter(
            models.APIToken.token == api_key,
            models.APIToken.is_active == True,
            models.APIToken.expires_at > datetime.utcnow() # เช็คว่ายังไม่หมดอายุ
        )
    )
    token_record = result.scalars().first()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key ไม่ถูกต้อง ถูกระงับ หรือหมดอายุแล้ว",
        )

    # 2. ค้นหา User ที่เป็นเจ้าของ Key นี้
    user_result = await db.execute(
        select(models.User).filter(
            models.User.id == token_record.user_id,
            models.User.is_deleted == False # เช็คว่า User ยังไม่ถูก Soft Delete
        )
    )
    user = user_result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ไม่พบผู้ใช้งานที่เป็นเจ้าของ API Key นี้ (อาจถูกลบไปแล้ว)",
        )

    return user