import time
import requests
import concurrent.futures
import statistics
import os
import glob
import random

API_URL = "http://127.0.0.1:8000/api/scan-slip/" 
# API_URL = "http://159.65.8.69/scan-slip/"
FOLDER_PATH = "./test-2" 
CONCURRENT_USERS = 10  
api_key = "sk_JTXILkSI65A0aXJB6BPARM8YugPmshzwPRjOx8w2vV8"
# กวาดหารูปภาพ
image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']
image_files = []
for ext in image_extensions:
    image_files.extend(glob.glob(os.path.join(FOLDER_PATH, ext)))


test_queue = image_files * 1 

def send_request(img_path):
    """ฟังก์ชันจำลองพฤติกรรม 1 User"""
    
    headers = {
        "X-API-Key": api_key
    }
 
    with open(img_path, "rb") as f:
        files = {"file": (os.path.basename(img_path), f, "image/jpeg")}
        start_time = time.time()
        try:
            response = requests.post(API_URL, files=files, headers=headers, timeout=30)
            latency = time.time() - start_time
            
            # ดึง JSON ออกมาถ้ารันสำเร็จ (เพื่อเตรียมส่งกลับ)
            res_json = response.json() if response.status_code == 200 else {}
            
            #  ต้อง return 4 ตัวให้ตรงกับที่รอรับ
            return latency, response.status_code, os.path.basename(img_path), res_json
            
        except Exception as e:
            #  ตรง except ก็ต้อง return 4 ตัวด้วย (ใส่ {} เปล่าๆ ปิดท้าย)
            return 0, str(e), os.path.basename(img_path), {}


print("="*50)
print(f"🔥 สั่งกองทัพ {CONCURRENT_USERS} Users บุกยิง!")
print(f"📦 จำนวนรวมทั้งหมด: {len(test_queue)} Requests")
print("="*50)

start_test = time.time()
success_count = 0
fail_count = 0
latencies = []


# --- เริ่มต้นการยิงแบบไม่รอใคร ---
with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as executor:
    # 1. ส่งงานทั้งหมดเข้าคิว (ไม่รอผล)
    future_to_img = {executor.submit(send_request, img): img for img in test_queue}
    
    # 2. ใครทำเสร็จก่อน ให้แสดงผลทันที (as_completed)
    for i, future in enumerate(concurrent.futures.as_completed(future_to_img)):
        #  รับค่า res_json ที่ส่งมาจาก send_request เพิ่มเข้ามา
        latency, status_code, file_name, res_json = future.result()
        
        if status_code == 200:
            success_count += 1
            latencies.append(latency)
            
            #  ดึงข้อมูลจาก JSON
            ai_status = res_json.get("status", "N/A")
            confidence = res_json.get("confidence", 0.0)
            
            #  จัด Tag ให้สวยงามตามสถานะที่ API ตอบกลับมา
            if ai_status == "ผ่าน":
                tag = f"✅ {ai_status} ({confidence}%)"
            elif ai_status == "ไม่ผ่าน":
                tag = f"❌ {ai_status} ({confidence}%)"
            else:
                tag = f"⚠️ {ai_status} ({confidence}%)"
                
        else:
            fail_count += 1
            tag = f"💥 FAIL (HTTP {status_code})"
        
        # แสดงผล Real-time (ใช้ <16 เพื่อจัดช่องไฟให้ตรงกัน)
        current_rps = (i + 1) / (time.time() - start_test)
        print(f"[{i+1}/{len(test_queue)}] {tag:<16} | {file_name:<15} | {latency:.3f}s | Current RPS: {current_rps:.2f}")

total_time = time.time() - start_test

# ==========================================
# 📊 สรุปผล Report
# ==========================================
print("\n" + "="*50)
print("📊 สรุปพลังทำลายล้าง:")
print("="*50)
print(f"⏱️ เวลาที่ใช้รวม:   {total_time:.2f} วินาที")
print(f"✅ สำเร็จ: {success_count} | ❌ ล้มเหลว: {fail_count}")

if latencies:
    print("-" * 50)
    print(f"🚀 FINAL RPS: {len(test_queue) / total_time:.2f} รูป/วินาที")
    print(f"⚡ Latency เฉลี่ย: {statistics.mean(latencies):.3f} วินาที")
print("="*50)