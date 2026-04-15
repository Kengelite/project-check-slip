from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional

# นำเข้าไฟล์จากโฟลเดอร์หลัก
from database import get_db
import models
from dependencies import get_current_user

router = APIRouter(tags=["Roles"])

# ==========================================
# 📝 Pydantic Schemas (สำหรับรับข้อมูลจาก Client)
# ==========================================
class RoleCreate(BaseModel):
    name: str
    desc: Optional[str] = ""

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    desc: Optional[str] = None

# ==========================================
# 1. READ ALL (ดึงข้อมูลสิทธิ์ทั้งหมด) - โค้ดเดิมของคุณ
# ==========================================
@router.get("/roles")
async def get_roles(
    search: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    query = select(
        models.Role.id,
        models.Role.name,
        models.Role.description,
        func.count(models.User.id).label("users_count")
    ).outerjoin(models.User).group_by(models.Role.id)

    if search:
        query = query.filter(models.Role.name.ilike(f"%{search}%"))

    query = query.order_by(models.Role.id.asc())
    result = await db.execute(query)
    roles = [dict(row._mapping) for row in result.all()]

    return {
        "data": roles,
        "total_items": len(roles)
    }

# ==========================================
# 2. READ ONE (ดึงข้อมูลสิทธิ์แค่ 1 รายการตาม ID)
# ==========================================
@router.get("/roles/{role_id}")
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.Role).filter(models.Role.id == role_id))
    role = result.scalars().first()
    
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบข้อมูลกลุ่มสิทธิ์นี้")
        
    return role

# ==========================================
# 3. CREATE (สร้างกลุ่มสิทธิ์ใหม่)
# ==========================================
@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # เช็คว่าชื่อ Role ซ้ำไหม
    existing_role = await db.execute(select(models.Role).filter(models.Role.name == role_data.name))
    if existing_role.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ชื่อกลุ่มสิทธิ์นี้มีในระบบแล้ว")

    new_role = models.Role(
        name=role_data.name,
        description=role_data.description
    )
    db.add(new_role)
    await db.commit()
    await db.refresh(new_role)
    
    return {"message": "สร้างกลุ่มสิทธิ์สำเร็จ", "data": new_role}

# ==========================================
# 4. UPDATE (แก้ไขข้อมูลกลุ่มสิทธิ์)
# ==========================================
@router.put("/roles/{role_id}")
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.Role).filter(models.Role.id == role_id))
    role = result.scalars().first()
    
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบข้อมูลกลุ่มสิทธิ์นี้")

    # อัปเดตเฉพาะฟิลด์ที่มีการส่งค่ามา
    if role_data.name is not None:
        role.name = role_data.name
    if role_data.desc is not None:
        role.desc = role_data.description

    await db.commit()
    await db.refresh(role)
    
    return {"message": "อัปเดตข้อมูลสำเร็จ", "data": role}

# ==========================================
# 5. DELETE (ลบกลุ่มสิทธิ์)
# ==========================================
@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.Role).filter(models.Role.id == role_id))
    role = result.scalars().first()
    
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบข้อมูลกลุ่มสิทธิ์นี้")

    # (ตัวเลือกเสริม) ป้องกันการลบ Role ถ้ายังมี User ใช้งานอยู่
    user_count_result = await db.execute(select(func.count(models.User.id)).filter(models.User.role_id == role_id))
    user_count = user_count_result.scalar()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"ไม่สามารถลบได้ เนื่องจากมีผู้ใช้งานอยู่ในกลุ่มนี้ {user_count} คน"
        )

    await db.delete(role)
    await db.commit()
    
    return {"message": "ลบกลุ่มสิทธิ์สำเร็จ"}