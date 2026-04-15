import os
import cv2
import torch
import numpy as np
import boto3
from botocore.client import Config
from PIL import Image
from torchvision import transforms
from fastapi import WebSocket
import logging
from inference import get_model

logger = logging.getLogger(__name__)

# --- WebSocket Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# --- Cloudflare R2 ---
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-600e8a1da8f94410bd40b5d216e22bc0.r2.dev")

def upload_to_r2(file_bytes: bytes, object_name: str, content_type: str = "image/jpeg"):
    s3 = boto3.client('s3',
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name="auto"
    )
    s3.put_object(Bucket=R2_BUCKET_NAME, Key=object_name, Body=file_bytes, ContentType=content_type)
    if R2_PUBLIC_URL:
        clean_url = R2_PUBLIC_URL.rstrip('/')
        return f"{clean_url}/{object_name}"
    return object_name

# --- AI Models ---
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
slip_model = torch.load("slip_checker_model.pth", map_location=device, weights_only=False)
slip_model.eval()

ROBOFLOW_API_KEY = "YSmhK0fmys5XBp6l0e2i"
ROBOFLOW_SLIP_MODEL_ID = "dection-slip/2"
rf_slip_model = get_model(model_id=ROBOFLOW_SLIP_MODEL_ID, api_key=ROBOFLOW_API_KEY)

test_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

def resize_image(img, max_dim=1024):
    h, w = img.shape[:2]
    if max(h, w) <= max_dim: return img
    if h > w: new_h, new_w = max_dim, int(w * (max_dim / h))
    else: new_h, new_w = int(h * (max_dim / w)), max_dim
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

def resize_for_storage(img, max_dim=640):
    h, w = img.shape[:2]
    if max(h, w) <= max_dim: return img
    scale = max_dim / max(h, w)
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
def process_slip_logic(img_cv2: np.ndarray) -> dict:
    img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img_rgb)
    input_tensor = test_transform(img_pil).unsqueeze(0).to(device)
    
    # --- ด่านที่ 1: PyTorch Model ---
    with torch.no_grad():
        output = slip_model(input_tensor)
        probs = torch.softmax(output, dim=1)
        conf, pred = torch.max(probs, 1)
        
    pytorch_conf = conf.item()
    pytorch_pred = pred.item()
    
    # สร้างตัวแปรเก็บ Log เบื้องต้น
    stage1_result = {
        "model1_class": "Slip" if pytorch_pred == 1 else "Not a Slip",
        "model1_conf": round(pytorch_conf * 100, 2)
    }
    logger.info(f"Stage 1 (PyTorch): {stage1_result}")

    # ถ้าด่านแรกไม่ผ่าน (Confidence ต่ำกว่า 50% หรือทำนายว่าเป็นไม่ใช่สลิป)
    # 💡 ผมแนะนำให้ลดเกณฑ์ลงหน่อยเพื่อให้สลิปมีธีม (ชิบะ) หลุดไปด่านสองได้ครับ
    if pytorch_pred == 0 or pytorch_conf < 0.50: 
        return {
            "status": "ไม่ผ่าน", 
            "reason": "ไม่ผ่านด่านตรวจสอบเบื้องต้น (PyTorch)", 
            "confidence": pytorch_conf,
            "details": stage1_result # ส่งรายละเอียด Model 1 กลับไปด้วย
        }

    # --- ด่านที่ 2: Roboflow Model ---
    try:
        raw_result = rf_slip_model.infer(img_cv2)
        slip_check_result = raw_result[0].dict() if isinstance(raw_result, list) else raw_result.dict()
        
        is_real_slip = False
        highest_conf = 0.0
        detected_class = "None"
        
        if 'predictions' in slip_check_result:
            for p in slip_check_result['predictions']:
                # ดึงชื่อ Class ออกมาดู (ระวังเรื่องตัวพิมพ์เล็ก-ใหญ่ หรือภาษาไทย)
                p_class = p.get('class', p.get('class_name', '')).lower()
                p_conf = p['confidence']
                
                if p_conf > highest_conf:
                    highest_conf = p_conf
                    detected_class = p_class

                # ถ้าเจอคีย์เวิร์ดว่าเป็นสลิป และคะแนนผ่านเกณฑ์
                if 'slip' in p_class or 'โอนเงิน' in p_class:
                    if p_conf >= 0.70: # ปรับเกณฑ์ความเข้มงวดตามต้องการ
                        is_real_slip = True
                        break
        
        stage2_result = {
            "model2_class": detected_class,
            "model2_conf": round(highest_conf * 100, 2)
        }
        logger.info(f"Stage 2 (Roboflow): {stage2_result}")

        if not is_real_slip:
            return {
                "status": "ไม่ผ่าน", 
                "reason": f"AI ตรวจไม่พบว่าเป็นสลิป (Detected: {detected_class})", 
                "confidence": highest_conf,
                "model1": stage1_result,
                "model2": stage2_result
            }

        return {
            "status": "ผ่าน", 
            "reason": "ตรวจสอบสำเร็จ", 
            "confidence": highest_conf,
            "model1": stage1_result, # โชว์ว่า Model 1 เห็นยังไง
            "model2": stage2_result  # โชว์ว่า Model 2 เห็นยังไง
        }

    except Exception as e:
        logger.error(f"Error in Roboflow: {e}")
        return {
            "status": "ไม่มั่นใจ", 
            "reason": f"Error: {str(e)}", 
            "confidence": 0.0,
            "model1": stage1_result
        }