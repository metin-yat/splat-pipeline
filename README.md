# 3DGS-Pipeline: End-to-End Reconstruction Service

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi) ![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white) ![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54) ![NVIDIA](https://img.shields.io/badge/NVIDIA-Container_Toolkit-76B900?style=for-the-badge&logo=nvidia&logoColor=white)

An automated, containerized pipeline that bridges raw video data and high-fidelity 3D environments — automating the full **2D → 3D radiance field** transition via **Structure-from-Motion** and **3D Gaussian Splatting**. Built as a hands-on deep-dive into Computer Vision engineering and scalable ML infrastructure. Paired with a custom-built Android client that streams video directly to the pipeline over local network — enabling full mobile-to-3D capture without any manual file transfer.

---

## Tech Stack

| Category | Technology |
|---|---|
| **Backend** | FastAPI (async) |
| **3D Reconstruction** | COLMAP — SfM + sparse mapping |
| **Neural Rendering** | Nerfstudio `splatfacto` |
| **Image Processing** | OpenCV |
| **Infrastructure** | Docker Compose · NVIDIA Container Toolkit |
| **Mobile Client** | Custom Android app — Wi-Fi video upload over local network |

---

## Architecture & Key Challenges

- **Async job orchestration** — SfM and neural rendering are computationally expensive; tasks are offloaded as background workers via FastAPI to prevent request blocking
- **GPU passthrough in containers** — configured NVIDIA Container Toolkit to expose host GPU inside Docker, enabling CUDA-accelerated COLMAP feature extraction and Nerfstudio training
- **Multi-container networking** — backend and splatting worker communicate over a dedicated Docker bridge network, keeping services decoupled and independently scalable
- **COLMAP → Nerfstudio data handoff** — implemented a custom conversion layer that parses COLMAP's sparse reconstruction output and generates Nerfstudio's required `transforms.json`, encoding camera intrinsics, extrinsics, and per-frame image paths
- **Mobile-to-pipeline integration** — built a companion Android app that uploads videos to the backend over local network via IP, enabling an end-to-end capture workflow: record on phone → transfer over Wi-Fi → reconstruct on GPU

---

## Quickstart
```bash
# Prerequisites: NVIDIA Container Toolkit on host
git clone https://github.com/metin-yat/splat-pipeline.git
cd splat-pipeline
docker-compose up --build
```

---

## Workflow

### 1. Upload & Frame Extraction
```bash
curl -X POST -F "video=@/path/to/your/video.mp4" http://localhost:8000/upload-video
curl -X POST http://localhost:8000/extract-frames/video_name.mp4
```

### 2. COLMAP Sparse Reconstruction
```bash
curl -X POST http://localhost:8000/run-colmap/video_name.mp4
```

### 3. Training & Monitoring
```bash
curl -X POST http://localhost:8000/start-pipeline/video_name.mp4
curl -X GET "http://localhost:8000/task-status/video_name"
tail -f data/logs/backend.log
```

### 4. Model Export
```bash
curl -X POST "http://localhost:8000/start-export/video_name?config_folder=2026-02-28_104906" \
  -H "Content-Type: application/json"
```