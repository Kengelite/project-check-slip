FROM python:3.10-slim
WORKDIR /app

# 🟢 ติดตั้ง System Libraries (เพิ่มพวก build-essential และ cmake สำหรับการคอมไพล์)
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    g++ \
    gcc \
    libgl1 \
    libglib2.0-0 \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

# ติดตั้ง Python Libraries
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-multipart \
    opencv-python-headless \
    numpy \
    pyzbar \
    torch \
    torchvision \
    inference

COPY . /app/

# ใช้พอร์ต 8000 เพื่อส่งต่อให้ Nginx
EXPOSE 8000

# รัน 1 worker ต่อ 1 container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]