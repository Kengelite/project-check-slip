import time
import requests
import concurrent.futures
import statistics
import os
import glob

# ==========================================
# ⚙️ ตั้งค่าการทดสอบ
# ==========================================
API_URL = "http://127.0.0.1:8000/scan-slip/" 
FOLDER_PATH = "./test"  # 👈 ชื่อโฟลเดอร์ที่เก็บรูปทดสอบของคุณ
CONCURRENT_USERS = 10          # ยิงพร้อมกันกี่คน

# กวาดหารูปภาพทั้งหมดในโฟลเดอร์
image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']
image_files = []
for ext in image_extensions:
    image_files.extend(glob.glob(os.path.join(FOLDER_PATH, ext)))

TOTAL_IMAGES = len(image_files)

if TOTAL_IMAGES == 0:
    print(f"❌ ไม่เจอรูปภาพในโฟลเดอร์ '{FOLDER_PATH}' เลยครับ!")
    exit()

# แก้ใน benchmark.py หรือ benchmark_folder.py
def send_request(img_path):
    with open(img_path, "rb") as f:
        # ระบุ Content-Type เข้าไปด้วย (image/jpeg)
        files = {"file": (os.path.basename(img_path), f, "image/jpeg")} 
        start_time = time.time()
        try:
            response = requests.post(API_URL, files=files)
            return time.time() - start_time, response.status_code, os.path.basename(img_path)
        except Exception as e:
            return 0, str(e), os.path.basename(img_path)
        

print("="*50)
print(f"🚀 เริ่มต้น Benchmark ด้วยรูปภาพในโฟลเดอร์")
print(f"📂 Folder: {FOLDER_PATH}")
print(f"📦 จำนวนรูปภาพทั้งหมด: {TOTAL_IMAGES} รูป")
print(f"🚦 Concurrent Workers: {CONCURRENT_USERS}")
print("="*50)

start_test = time.time()
success_count = 0
fail_count = 0
latencies = []

# ใช้ ThreadPool เพื่อรันงานขนานกัน
with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as executor:
    # ส่ง list ของไฟล์ภาพเข้าไปทำงาน
    results = list(executor.map(send_request, image_files))

for latency, status, file_name in results:
    if status == 200:
        success_count += 1
        latencies.append(latency)
        print(f"✅ {file_name}: OK ({latency:.3f}s)")
    else:
        fail_count += 1
        print(f"❌ {file_name}: Failed/Rejected (Status: {status})")

total_time = time.time() - start_test

# ==========================================
# 📊 สรุปผล Report
# ==========================================
print("\n" + "="*50)
print("📊 สรุปผลการทดสอบรายโฟลเดอร์:")
print("="*50)
print(f"⏱️ เวลาที่ใช้รวม:   {total_time:.2f} วินาที")
print(f"✅ สำเร็จ (200):   {success_count} รูป")
print(f"❌ ไม่ผ่าน (Error): {fail_count} รูป")

if latencies:
    avg_latency = statistics.mean(latencies)
    rps = TOTAL_IMAGES / total_time
    print("-" * 50)
    print(f"🚀 เฉลี่ยความเร็วระบบ (RPS): {rps:.2f} รูป/วินาที")
    print(f"⚡ Latency เฉลี่ยต่อรูป:      {avg_latency:.3f} วินาที")
print("="*50)