import uuid
import cv2
import numpy as np
import math
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from starlette.concurrency import run_in_threadpool

from database import get_db
import models
from dependencies import get_current_user,  verify_api_key
from utils import resize_image, resize_for_storage, process_slip_logic, upload_to_r2, manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Slip Scanner"])

# ==========================================
# 📡 WebSocket
# ==========================================
@router.websocket("/ws/slips")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: 
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ==========================================
# 📸 สแกนสลิป
# ==========================================
@router.post("/scan-slip/")
async def scan_slip(
    file: UploadFile = File(...), 
    db: AsyncSession = Depends(get_db), 
    #  เปลี่ยนจาก get_current_user เป็น verify_api_key ตรงนี้ครับ!
    current_user: models.User = Depends(verify_api_key) 
):
    # ... โค้ดที่เหลือเหมือนเดิม 100% เลยครับ ...
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type.")
    
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img_cv2 is None:
        raise HTTPException(status_code=400, detail="Could not decode image.")
    
    img_cv2 = resize_image(img_cv2, max_dim=1024)
    result = await run_in_threadpool(process_slip_logic, img_cv2)
    
    ai_status = result["status"]
    ai_reason = result["reason"]
    ai_confidence = round(result["confidence"] * 100, 2)
    result["confidence"] = ai_confidence 

    if ai_status == "ผ่าน":
        prefix = "slip"
    elif ai_status == "ไม่ผ่าน":
        prefix = "rejected"
    else:
        prefix = "unknown"
        
    file_name = f"{prefix}_{uuid.uuid4().hex[:8]}.jpg"
    logger.info(f"📁 Processed image: {file_name} (Status: {ai_status}, Confidence: {ai_confidence}%)")
    
    status_mapping = {
        "ผ่าน": 1,
        "ไม่ผ่าน": 2,
        "ไม่มั่นใจ": 3
    }
    db_status_id = status_mapping.get(ai_status, 3) 
    
    storage_img = resize_for_storage(img_cv2, max_dim=640)
    _, encoded_image = cv2.imencode('.jpg', storage_img, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
    image_bytes = encoded_image.tobytes()
   
    try:
        image_url = await run_in_threadpool(upload_to_r2, image_bytes, file_name)
    except Exception as e:
        logger.error(f"Failed to upload to R2: {e}")
        raise HTTPException(status_code=500, detail="ระบบจัดเก็บรูปภาพขัดข้อง")

    new_slip = models.Slip(
        filename=image_url,     
        status_id=db_status_id, 
        reason=ai_reason,
        confidence=float(ai_confidence),
        payload={}              
    )
    db.add(new_slip)
    await db.commit()
    await db.refresh(new_slip)

    # 📣 🟢 ยิง WebSocket แจ้งเตือนทุกคนว่ามีสลิปใหม่!
    await manager.broadcast({
        "event": "new_slip", 
        "id": str(new_slip.id),
        "status": ai_status
    })

    result["db_id"] = str(new_slip.id)
    result["filename"] = file_name
    result["image_url"] = image_url

    return JSONResponse(content=result, status_code=200)

# ==========================================
# 📊 สถิติ (Dashboard)
# ==========================================
@router.get("/stats")
async def get_stats(
    search: str = "", 
    time: str = "all", 
    status: str = "all", 
    db: AsyncSession = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    query = select(models.Slip).join(models.StatusSlip)

    if search:
        query = query.filter(models.Slip.filename.ilike(f"%{search}%"))

    if status != "all":
        query = query.filter(models.StatusSlip.name.ilike(status))

    if time != "all":
        now = datetime.utcnow()
        time_map = {
            "1h": timedelta(hours=1), "6h": timedelta(hours=6),
            "1d": timedelta(days=1), "3d": timedelta(days=3), "5d": timedelta(days=5),
            "1w": timedelta(weeks=1), "2w": timedelta(weeks=2), "3w": timedelta(weeks=3),
            "1m": timedelta(days=30)
        }
        if time in time_map:
            query = query.filter(models.Slip.created_at >= now - time_map[time])

    total_res = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_res.scalar() or 0

    success_query = query.filter(models.StatusSlip.name.ilike("ผ่าน"))
    success_res = await db.execute(select(func.count()).select_from(success_query.subquery()))
    success = success_res.scalar() or 0

    rejected_query = query.filter(models.StatusSlip.name.ilike("ไม่ผ่าน"))
    rejected_res = await db.execute(select(func.count()).select_from(rejected_query.subquery()))
    rejected = rejected_res.scalar() or 0

    return {
        "total": total,
        "ผ่าน": success,
        "ไม่ผ่าน": rejected
    }

# ==========================================
# 📋 รายการสลิปทั้งหมด
# ==========================================
@router.get("/slips")
async def get_slips(
    search: str = "", 
    time: str = "all", 
    status: str = "all", 
    page: int = Query(1, ge=1), 
    limit: int = Query(10, ge=1), 
    db: AsyncSession = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    query = select(
        models.Slip.id,
        models.Slip.filename,
        models.Slip.confidence,
        models.Slip.created_at,
        models.StatusSlip.name.label("status_name")
    ).join(models.StatusSlip)

    if search:
        query = query.filter(models.Slip.filename.ilike(f"%{search}%"))

    if status != "all":
        query = query.filter(models.StatusSlip.name.ilike(status))

    if time != "all":
        now = datetime.utcnow()
        time_map = {
            "1h": timedelta(hours=1), "6h": timedelta(hours=6),
            "1d": timedelta(days=1), "3d": timedelta(days=3), "5d": timedelta(days=5),
            "1w": timedelta(weeks=1), "2w": timedelta(weeks=2), "3w": timedelta(weeks=3),
            "1m": timedelta(days=30)
        }
        if time in time_map:
            query = query.filter(models.Slip.created_at >= now - time_map[time])

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_items = total_result.scalar() or 0

    offset = (page - 1) * limit
    query = query.order_by(models.Slip.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    slips = [dict(row._mapping) for row in result.all()]

    total_pages = math.ceil(total_items / limit) if total_items > 0 else 1

    return {
        "data": slips,
        "pagination": {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "limit": limit
        }
    }

# ==========================================
# ✅ รายการสลิปเฉพาะที่ "ผ่าน"
# ==========================================
@router.get("/slips/passed")
async def get_passed_slips(
    search: str = "", 
    time: str = "all", 
    page: int = Query(1, ge=1), 
    limit: int = Query(10, ge=1), 
    db: AsyncSession = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    query = select(
        models.Slip.id,
        models.Slip.filename,
        models.Slip.confidence,
        models.Slip.created_at,
        models.StatusSlip.name.label("status_name")
    ).join(models.StatusSlip)

    query = query.filter(models.StatusSlip.name.ilike("ผ่าน"))

    if search:
        query = query.filter(models.Slip.filename.ilike(f"%{search}%"))

    if time != "all":
        now = datetime.utcnow()
        time_map = {
            "1h": timedelta(hours=1), "6h": timedelta(hours=6),
            "1d": timedelta(days=1), "3d": timedelta(days=3), "5d": timedelta(days=5),
            "1w": timedelta(weeks=1), "2w": timedelta(weeks=2), "3w": timedelta(weeks=3),
            "1m": timedelta(days=30)
        }
        if time in time_map:
            query = query.filter(models.Slip.created_at >= now - time_map[time])

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_items = total_result.scalar() or 0

    offset = (page - 1) * limit
    query = query.order_by(models.Slip.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    slips = [dict(row._mapping) for row in result.all()]

    total_pages = math.ceil(total_items / limit) if total_items > 0 else 1

    return {
        "data": slips,
        "pagination": {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "limit": limit
        }
    }

# ==========================================
# ❌ รายการสลิปเฉพาะที่ "ไม่ผ่าน"
# ==========================================
@router.get("/slips/failed")
async def get_failed_slips(
    search: str = "", 
    time: str = "all", 
    page: int = Query(1, ge=1), 
    limit: int = Query(10, ge=1), 
    db: AsyncSession = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    query = select(
        models.Slip.id,
        models.Slip.filename,
        models.Slip.confidence,
        models.Slip.created_at,
        models.StatusSlip.name.label("status_name")
    ).join(models.StatusSlip)

    query = query.filter(models.StatusSlip.name.ilike("ไม่ผ่าน"))

    if search:
        query = query.filter(models.Slip.filename.ilike(f"%{search}%"))

    if time != "all":
        now = datetime.utcnow()
        time_map = {
            "1h": timedelta(hours=1), "6h": timedelta(hours=6),
            "1d": timedelta(days=1), "3d": timedelta(days=3), "5d": timedelta(days=5),
            "1w": timedelta(weeks=1), "2w": timedelta(weeks=2), "3w": timedelta(weeks=3),
            "1m": timedelta(days=30)
        }
        if time in time_map:
            query = query.filter(models.Slip.created_at >= now - time_map[time])

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_items = total_result.scalar() or 0

    offset = (page - 1) * limit
    query = query.order_by(models.Slip.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    slips = [dict(row._mapping) for row in result.all()]

    total_pages = math.ceil(total_items / limit) if total_items > 0 else 1

    return {
        "data": slips,
        "pagination": {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "limit": limit
        }
    }