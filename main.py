import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from sqlalchemy.future import select

from database import engine, Base, AsyncSessionLocal
import models
from dependencies import get_password_hash

# 📥 ดึง Routers ที่เราแยกไว้เข้ามา
from routers import auth, slips, roles, pages , user , key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from starlette.middleware.sessions import SessionMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("⏳ Connecting to PostgreSQL and creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(" Database tables ready!")
    
    async with AsyncSessionLocal() as db:
        
        # ---------------------------------------------------------
        # 1. ตั้งค่า Default StatusSlip (สถานะของสลิป)
        # ---------------------------------------------------------
        default_statuses = [
            {"id": 1, "name": "ผ่าน", "description": "สลิปถูกต้องตามการตรวจสอบ"},
            {"id": 2, "name": "ไม่ผ่าน", "description": "สลิปปลอม, ยอดเงินไม่ตรง หรือผิดปกติ"},
            {"id": 3, "name": "ไม่มั่นใจ", "description": "AI ไม่แน่ใจ ต้องให้พนักงานตรวจสอบ"}
        ]
        for stat in default_statuses:
            result = await db.execute(select(models.StatusSlip).filter_by(name=stat["name"]))
            if not result.scalars().first():
                new_status = models.StatusSlip(name=stat["name"], description=stat["description"])
                db.add(new_status)
                logger.info(f"✅ Default Status created: {stat['name']}")

        # ---------------------------------------------------------
        # 2. ตั้งค่า Default Roles (สิทธิ์การใช้งาน)
        # ---------------------------------------------------------
        default_roles = [
            {"id": 0,"name": "Super Admin", "description": "ผู้ดูแลระบบสูงสุด จัดการได้ทุกอย่าง"},
            {"id": 1,"name": "Staff", "description": "พนักงานตรวจสอบสลิปทั่วๆ ไป"}
        ]
        for r in default_roles:
            result = await db.execute(select(models.Role).filter_by(name=r["name"]))
            if not result.scalars().first():
                new_role = models.Role(name=r["name"], description=r["description"])
                db.add(new_role)
                logger.info(f"✅ Default Role created: {r['name']}")

        # Commit บันทึก Status และ Role ลงฐานข้อมูลก่อน เพื่อให้ดึง ID มาใช้ต่อได้
        await db.commit()

        # ---------------------------------------------------------
        # 3. ตั้งค่า Default Super Admin User
        # ---------------------------------------------------------
        admin_email = "admin@slipscanner.com"
        result = await db.execute(select(models.User).filter_by(email=admin_email))
        admin = result.scalars().first()
        
        if not admin:
            # ค้นหา ID ของ Role "Super Admin" ที่เพิ่งสร้างไป
            role_result = await db.execute(select(models.Role).filter_by(name="Super Admin"))
            super_admin_role = role_result.scalars().first()

            if super_admin_role:
                new_admin = models.User(
                    email=admin_email,
                    hashed_password=get_password_hash("123456789"), # รหัสผ่านเริ่มต้น
                    full_name="ผู้ดูแลระบบ (Admin)",
                    role_id=super_admin_role.id,
                    is_deleted=False # เพราะใน model ใช้ SoftDeleteMixin (nullable)
                )
                db.add(new_admin)
                await db.commit()
                logger.info(f"👤 Default Admin created: {admin_email} / password123")

    yield
app = FastAPI(title="Superfast Slip API (Secure)", version="1.0", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key="my-super-secret-session-key")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🚀 เสียบ Routers เข้ากับแอปหลัก
app.include_router(auth.router, prefix="/api")
app.include_router(slips.router, prefix="/api")
app.include_router(roles.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(key.router, prefix="/api")
# ส่วน pages (หน้าเว็บ HTML) ไม่ต้องมี /api นำหน้า ให้ดึงมาใส่เพียวๆ เลย
app.include_router(pages.router)
# Mount โฟลเดอร์รูปและ Static
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "frontend")), name="frontend")