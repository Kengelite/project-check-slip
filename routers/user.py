from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, update
from pydantic import BaseModel, EmailStr
from typing import Optional
import math
from datetime import datetime

# นำเข้าไฟล์จากโฟลเดอร์หลัก
from database import get_db 
import models         
from dependencies import get_current_user, get_password_hash

router = APIRouter(tags=["Users"])

# ==========================================
# 📝 Pydantic Schemas
# ==========================================
class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role_id: int

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role_id: Optional[int] = None
    # ไม่แนะนำให้อัปเดต password ในเส้นนี้ ควรแยกเป็น /change-password

# ==========================================
# 1. READ ALL (ดึงเฉพาะคนที่ยังไม่ถูกลบ)
# ==========================================
@router.get("/users")
async def get_users(
    search: str = "",
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # กรองเอาเฉพาะ is_deleted == False
    query = select(
        models.User.id,
        models.User.full_name.label("name"),
        models.User.email,
        models.Role.name.label("role_name"),
        models.User.role_id
    ).join(models.Role).filter(models.User.is_deleted == False)

    if search:
        query = query.filter(
            or_(
                models.User.full_name.ilike(f"%{search}%"),
                models.User.email.ilike(f"%{search}%")
            )
        )

    # Pagination Logic
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_items = total_result.scalar() or 0

    offset = (page - 1) * limit
    query = query.order_by(models.User.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    users = [dict(row._mapping) for row in result.all()]
    total_pages = math.ceil(total_items / limit) if total_items > 0 else 1

    return {
        "data": users,
        "pagination": {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "limit": limit
        }
    }

# ==========================================
# 2. CREATE (สร้าง User ใหม่)
# ==========================================
@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # เช็ค Email ซ้ำ
    existing = await db.execute(select(models.User).filter(models.User.email == user_in.email))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="อีเมลนี้ถูกใช้งานแล้ว")

    new_user = models.User(
        full_name=user_in.full_name,
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        role_id=user_in.role_id,
        is_deleted=False  # เปลี่ยนเป็น None เพื่อบันทึกค่า NULL ลง Database
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"message": "สร้างผู้ใช้งานสำเร็จ", "id": str(new_user.id)}
# ==========================================
# 3. UPDATE
# ==========================================
@router.put("/users/{user_id}")
async def update_user(
    user_id: str, # ใช้ str เพราะเป็น UUID
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.User).filter(models.User.id == user_id, models.User.is_deleted == False))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งาน")

    if user_in.full_name is not None: user.full_name = user_in.full_name
    if user_in.email is not None: user.email = user_in.email
    if user_in.role_id is not None: user.role_id = user_in.role_id

    await db.commit()
    return {"message": "อัปเดตข้อมูลสำเร็จ"}

# ==========================================
# 4. DELETE (Soft Delete) 🗑️
# ==========================================
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ค้นหา User ที่ยังไม่ถูกลบ
    result = await db.execute(select(models.User).filter(models.User.id == user_id, models.User.is_deleted == False))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งาน หรือถูกลบไปแล้ว")

    # ทำ Soft Delete โดยเปลี่ยน Flag และบันทึกเวลาที่ลบ
    user.is_deleted = True
    user.deleted_at = datetime.utcnow()

    await db.commit()
    return {"message": "ลบผู้ใช้งานสำเร็จ (Soft Delete)"}