import os
import io
import cv2
import torch
import numpy as np
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from torchvision import transforms
from pyzbar.pyzbar import decode
from inference import get_model  # โหลดโมเดล Roboflow มาไว้ในเครื่อง (Local)
from starlette.concurrency import run_in_threadpool
import logging

# --- ตั้งค่า Configuration ---
MODEL_PATH = "slip_checker_model.pth" 
ROBOFLOW_API_KEY = "YSmhK0fmys5XBp6l0e2i"
ROBOFLOW_QR_MODEL_ID = "project-slip-qr/4"  
ROBOFLOW_SLIP_MODEL_ID = "dection-slip/2" 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- โหลด AI รอไว้ใน RAM ---
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"🚀 Starting server on: {device}")

try:
    slip_model = torch.load(MODEL_PATH, map_location=device, weights_only=False)
    slip_model.eval()
except Exception as e:
    logger.error(f"❌ Failed to load PyTorch: {e}")
    raise e

test_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

try:
    logger.info("⏳ Loading Roboflow Models locally...")
    rf_slip_model = get_model(model_id=ROBOFLOW_SLIP_MODEL_ID, api_key=ROBOFLOW_API_KEY)
    rf_qr_model = get_model(model_id=ROBOFLOW_QR_MODEL_ID, api_key=ROBOFLOW_API_KEY)
except Exception as e:
    logger.error(f"❌ Failed to load Roboflow models: {e}")
    raise e

app = FastAPI(title="Superfast Slip API", version="1.0")

# --- ฟังก์ชันแต่งภาพ 4 สูตร ---
def get_enhanced_qrs(cropped_qr):
    variations = []
    resized = cv2.resize(cropped_qr, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    
    variations.append(("Basic", gray))
    _, th1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    variations.append(("Otsu", th1))
    bilateral = cv2.bilateralFilter(gray, 9, 75, 75)
    th2 = cv2.adaptiveThreshold(bilateral, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 2)
    variations.append(("Bilateral", th2))
    kernel = np.ones((3,3), np.uint8)
    th3 = cv2.dilate(th2, kernel, iterations=1) 
    variations.append(("Dilate", th3))
    return variations

# --- Core Logic การประมวลผล ---
def process_slip_logic(img_cv2: np.ndarray) -> dict:
    # 🛑 ด่าน 1: PyTorch (กฎ 80%)
    img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img_rgb)
    input_tensor = test_transform(img_pil).unsqueeze(0).to(device)
    
    with torch.no_grad():
        output = slip_model(input_tensor)
        probs = torch.softmax(output, dim=1)
        conf, pred = torch.max(probs, 1)
        
    pytorch_conf = conf.item()
    if pred.item() == 0 or pytorch_conf < 0.80:
        return {"status": "rejected", "reason": "Not a slip (PyTorch)", "confidence": pytorch_conf}

    # 🕵️‍♂️ ด่าน 1.5: Roboflow Local (กฎ 80%)
    try:
        raw_result = rf_slip_model.infer(img_cv2)
        slip_check_result = raw_result[0].dict() if isinstance(raw_result, list) else raw_result.dict()
        is_real_slip = False
        if 'predictions' in slip_check_result:
            for p in slip_check_result['predictions']:
                if 'slip' in p['class'].lower() and p['confidence'] >= 0.80:
                    is_real_slip = True
                    break
        if not is_real_slip:
            return {"status": "rejected", "reason": "Not a slip (Roboflow)"}
    except Exception as e:
        logger.warning(f"Roboflow check failed: {e}")

    # ⚡ ด่าน 2: สแกนรูปเต็ม
    qr_data_list = []
    decoded_objects = decode(img_cv2)
    if decoded_objects:
        for obj in decoded_objects:
            qr_data_list.append(obj.data.decode("utf-8"))
        return {"status": "success", "method": "direct", "payload": qr_data_list}
    
    # 🛠️ ด่าน 3: Roboflow Crop + Filters
    try:
        raw_qr_result = rf_qr_model.infer(img_cv2)
        result = raw_qr_result[0].dict() if isinstance(raw_qr_result, list) else raw_qr_result.dict()
        predictions = result.get('predictions', [])
        if not predictions:
            return {"status": "failed", "reason": "QR code not found"}
            
        detector = cv2.QRCodeDetector()
        for pred in predictions:
            x_min = max(0, int(pred['x'] - (pred['width'] / 2)))
            y_min = max(0, int(pred['y'] - (pred['height'] / 2)))
            x_max = int(pred['x'] + (pred['width'] / 2))
            y_max = int(pred['y'] + (pred['height'] / 2))
            
            cropped_qr = img_cv2[y_min:y_max, x_min:x_max]
            variations = get_enhanced_qrs(cropped_qr)
            
            for filter_name, enhanced_img in variations:
                decoded_enhanced = decode(enhanced_img)
                if decoded_enhanced:
                    for obj in decoded_enhanced:
                        qr_data_list.append(obj.data.decode("utf-8"))
                    return {"status": "success", "method": f"filter_{filter_name}", "payload": qr_data_list}
                
                data, _, _ = detector.detectAndDecode(enhanced_img)
                if data:
                    qr_data_list.append(data)
                    return {"status": "success", "method": f"opencv_{filter_name}", "payload": qr_data_list}
        return {"status": "failed", "reason": "Unreadable QR"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}

# --- API Endpoint ---
@app.post("/scan-slip/")
async def scan_slip(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type.")
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_cv2 is None:
        raise HTTPException(status_code=400, detail="Could not decode image.")
        
    result = await run_in_threadpool(process_slip_logic, img_cv2)
    return JSONResponse(content=result, status_code=200 if result["status"] == "success" else 400)