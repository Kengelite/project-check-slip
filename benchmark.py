import time
import requests
import concurrent.futures
import statistics
import os

# ==========================================
# ⚙️ ตั้งค่าการทดสอบ (ปรับเปลี่ยนได้ตามใจชอบ)
# ==========================================
API_URL = "http://127.0.0.1:8000/scan-slip/"  # ถ้าเทสบนเซิร์ฟเวอร์จริง ให้เปลี่ยนเป็น IP เซิร์ฟเวอร์
IMAGE_PATH = "test_slip.jpg"                  # ชื่อไฟล์รูปสลิปที่คุณจะใช้เทส (ต้องมีไฟล์นี้อยู่จริง)

TOTAL_REQUESTS = 100    # จำนวนรูปรวมทั้งหมดที่จะยิงเข้าไป
CONCURRENT_USERS = 10   # จำนวนคนยิงพร้อมกัน (ยิ่งเยอะ เซิร์ฟเวอร์ยิ่งทำงานหนัก)

# เช็คก่อนว่ามีไฟล์รูปไหม จะได้ไม่ Error ดื้อๆ
if not os.path.exists(IMAGE_PATH):
    print(f"❌ หาไฟล์รูป '{IMAGE_PATH}' ไม่เจอครับ รบกวนเอามาวางไว้โฟลเดอร์เดียวกันก่อนนะ")
    exit()

def send_request(req_id):
    """ฟังก์ชันสำหรับยิง 1 Request"""
    # ต้องเปิดไฟล์ใหม่ทุกครั้งในแต่ละ Thread ป้องกัน Error ไฟล์ชนกัน
    with open(IMAGE_PATH, "rb") as f:
        files = {"file": f}
        start_time = time.time()
        try:
            response = requests.post(API_URL, files=files)
            latency = time.time() - start_time
            return latency, response.status_code
        except Exception as e:
            return 0, str(e)

print("="*40)
print(f"🚀 เริ่มต้นการทำ Benchmark API ตรวจสลิป")
print(f"🎯 เป้าหมาย: {API_URL}")
print(f"📦 จำนวนรวม: {TOTAL_REQUESTS} requests")
print(f"🚦 ยิงพร้อมกัน: {CONCURRENT_USERS} concurrent workers")
print("="*40)
print("กำลังยิงรัวๆ กรุณารอสักครู่...\n")

start_test = time.time()
success_count = 0
fail_count = 0
latencies = []

# ใช้ ThreadPoolExecutor เพื่อจำลองคนเข้าใช้งานพร้อมกัน
with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as executor:
    results = executor.map(send_request, range(TOTAL_REQUESTS))
    
    for latency, status in results:
        if status == 200:
            success_count += 1
            latencies.append(latency)
        else:
            fail_count += 1

total_time = time.time() - start_test

# ==========================================
# 📊 สรุปผลลัพธ์การทดสอบ
# ==========================================
print("="*40)
print("📊 สรุปผล Benchmark (Report):")
print("="*40)
print(f"⏱️ เวลาที่ใช้ทั้งหมด:  {total_time:.2f} วินาที")
print(f"✅ ยิงสำเร็จ (200 OK): {success_count} ครั้ง")
print(f"❌ ยิงพลาด/โดนเตะ:    {fail_count} ครั้ง")

if latencies:
    avg_latency = statistics.mean(latencies)
    max_latency = max(latencies)
    min_latency = min(latencies)
    rps = TOTAL_REQUESTS / total_time
    
    print("-" * 40)
    print(f"🚀 Requests Per Second (RPS): {rps:.2f} req/sec")
    print(f"⚡ ความเร็วเฉลี่ยต่อรูป:        {avg_latency:.3f} วินาที")
    print(f"🐢 ช้าที่สุด (Max Latency):   {max_latency:.3f} วินาที")
    print(f"🐇 เร็วที่สุด (Min Latency):   {min_latency:.3f} วินาที")
print("="*40)