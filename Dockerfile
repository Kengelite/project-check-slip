FROM python:3.10-slim
WORKDIR /app

# ติดตั้ง System Library ให้ pyzbar และ OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

    
# ติดตั้ง Python Libraries
RUN pip install --no-cache-dir fastapi uvicorn python-multipart opencv-python-headless numpy pyzbar torch torchvision inference

COPY . /app/
EXPOSE 80

# สั่งรัน API (ปรับ --workers ตามจำนวน CPU คอร์ของเซิร์ฟเวอร์)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "4"]