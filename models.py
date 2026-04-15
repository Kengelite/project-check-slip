import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base



class SoftDeleteMixin:
    """
    คลาสเสริมสำหรับใส่เข้าไปใน Table ไหนก็ได้ที่อยากทำ Soft Delete
    """
    # เพิ่ม nullable=False เพื่อบังคับให้ต้องเป็น True หรือ False เท่านั้น ห้ามเป็น NULL
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    def soft_delete(self):
        """เรียกใช้ฟังก์ชันนี้เมื่อต้องการลบ (Soft Delete)"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

    def restore(self):
        """เรียกใช้ฟังก์ชันนี้เมื่อต้องการกู้คืนข้อมูล"""
        self.is_deleted = False
        self.deleted_at = None


class Role(Base):
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)
    
    users = relationship("User", back_populates="role")

class StatusSlip(Base):
    __tablename__ = "status_slips"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)
    
    slips = relationship("Slip", back_populates="status")

class User(Base, SoftDeleteMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role_id = Column(Integer, ForeignKey("roles.id"))
    
    #  เพิ่ม Timestamp ตรงนี้
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) # อัปเดตอัตโนมัติ

    role = relationship("Role", back_populates="users")
   

class Slip(Base, SoftDeleteMixin):
    __tablename__ = "slips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, index=True)
    status_id = Column(Integer, ForeignKey("status_slips.id"))
    reason = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    payload = Column(JSONB, nullable=True)
    
    #  เพิ่ม Timestamp ตรงนี้
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) # อัปเดตอัตโนมัติ

    status = relationship("StatusSlip", back_populates="slips")
  


class APIToken(Base):
    __tablename__ = "api_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    token = Column(String, unique=True, index=True, nullable=False)
    
    is_active = Column(Boolean, default=True) # เอาไว้ปิดการใช้งาน (Revoke) Token นี้
    expires_at = Column(DateTime, nullable=False) # วันหมดอายุ
    created_at = Column(DateTime, default=datetime.utcnow)

    # ความสัมพันธ์กลับไปยังตาราง User (ถ้ามี)
    # user = relationship("User", back_populates="tokens")