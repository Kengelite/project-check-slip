from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from pydantic import BaseModel
from typing import Optional
import math
import secrets
from datetime import datetime, timedelta

# นำเข้าไฟล์จากโฟลเดอร์หลัก
from database import get_db
import models
from dependencies import get_current_user

router = APIRouter(tags=["API Keys"])

# ==========================================
# 📝 Pydantic Schemas
# ==========================================
class KeyCreate(BaseModel):
    user_id: Optional[str] = None # ถ้าไม่ส่งมา จะใช้ ID ของคนที่ล็อกอินอยู่
    expires_in_days: int = 365    # ค่าเริ่มต้นให้หมดอายุใน 1 ปี

class KeyUpdate(BaseModel):
    is_active: bool

# ==========================================
# 1. READ ALL (ดึงข้อมูล Key ทั้งหมด พร้อม Pagination)
# ==========================================
@router.get("/keys")
async def get_keys(
    search: str = "",
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # JOIN ข้อมูล APIToken กับ User เพื่อเอาชื่อคนสร้างมาแสดง
    query = select(
        models.APIToken.id,
        models.APIToken.token,
        models.APIToken.is_active,
        models.APIToken.expires_at,
        models.User.full_name.label("user_name")
    ).join(models.User, models.APIToken.user_id == models.User.id)

    if search:
        query = query.filter(
            or_(
                models.APIToken.token.ilike(f"%{search}%"),
                models.User.full_name.ilike(f"%{search}%")
            )
        )

    # นับจำนวนทั้งหมด (Pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_items = total_result.scalar() or 0

    # ตัดหน้า (Offset & Limit)
    offset = (page - 1) * limit
    query = query.order_by(models.APIToken.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    keys = [dict(row._mapping) for row in result.all()]

    total_pages = math.ceil(total_items / limit) if total_items > 0 else 1

    return {
        "data": keys,
        "pagination": {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "limit": limit
        }
    }

# ==========================================
# 2. CREATE (สร้าง API Key ใหม่)
# ==========================================
@router.post("/keys", status_code=status.HTTP_201_CREATED)
async def create_key(
    key_in: KeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # สุ่มรหัส Token ความยาว 32 ตัวอักษร (ปลอดภัยสำหรับใช้เป็น API Key)
    generated_token = f"sk_{secrets.token_urlsafe(32)}"
    
    # คำนวณวันหมดอายุ
    expiration_date = datetime.utcnow() + timedelta(days=key_in.expires_in_days)
    
    # กำหนดเจ้าของ Token (ถ้าแอดมินไม่ได้ระบุ user_id มา ให้ใช้ ID ของคนที่กดสร้าง)
    owner_id = key_in.user_id if key_in.user_id else current_user.id

    new_key = models.APIToken(
        user_id=owner_id,
        token=generated_token,
        is_active=True,
        expires_at=expiration_date
    )
    
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    
    return {
        "message": "สร้าง API Key สำเร็จ", 
        "data": {
            "id": new_key.id,
            "token": new_key.token,
            "expires_at": new_key.expires_at
        }
    }

# ==========================================
# 3. UPDATE (เปิด/ปิด การใช้งาน Key)
# ==========================================
@router.put("/keys/{key_id}")
async def update_key_status(
    key_id: str,
    key_in: KeyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.APIToken).filter(models.APIToken.id == key_id))
    api_key = result.scalars().first()
    
    if not api_key:
        raise HTTPException(status_code=404, detail="ไม่พบ API Key นี้ในระบบ")

    # อัปเดตสถานะ (True = ใช้งาน, False = ระงับ)
    api_key.is_active = key_in.is_active

    await db.commit()
    return {"message": "อัปเดตสถานะ Key สำเร็จ"}

# ==========================================
# 4. DELETE (ลบ Key ออกจากระบบถาวร)
# ==========================================
@router.delete("/keys/{key_id}")
async def delete_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.APIToken).filter(models.APIToken.id == key_id))
    api_key = result.scalars().first()

    if not api_key:
        raise HTTPException(status_code=404, detail="ไม่พบ API Key นี้ในระบบ")

    await db.delete(api_key)
    await db.commit()
    
    return {"message": "ลบ API Key ถาวรสำเร็จ"}