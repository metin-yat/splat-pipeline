import shutil, re
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from rich.logging import RichHandler
from rich.console import Console

from utils import extract_frames_task, colmap_pipeline_task

app = FastAPI()
console = Console()

# Path Configurations ---
UPLOAD_DIR = Path("uploads")
DATA_DIR = Path("../data")
LOG_DIR = DATA_DIR / "logs"

UPLOAD_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Logging Setup       ---
log_file = LOG_DIR / "backend.log"

class PlainRichFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        # Clean tags ([bold], [blue], [/])
        clean_msg = re.sub(r"\[\/?[a-zA-Z ]+\]", "", msg)
        return clean_msg

file_formatter = PlainRichFormatter("%(asctime)s | %(levelname)s | %(message)s")

file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
file_handler.setFormatter(file_formatter)

rich_handler = RichHandler(rich_tracebacks=True, markup=True)

logger = logging.getLogger("VideoProcessor")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(rich_handler)

tasks_progress = {} # Global Task State 
is_system_busy = False

@app.get("/")
async def health_check():
    return {"status": "healthy", "service": "3dgs-backend", "busy": is_system_busy}

@app.post("/upload-video")
async def upload_video(video: UploadFile = File(...)):
    if not video.filename.endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Only .mp4 files are supported.")

    file_path = UPLOAD_DIR / video.filename
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
        logger.info(f"[bold green]File Uploaded:[/bold green] {video.filename}")
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during upload.")
    finally:
        video.file.close()

    return {"filename": video.filename, "message": "Upload successful"}

@app.post("/extract-frames/{video_name}")
async def start_extraction(video_name: str, background_tasks: BackgroundTasks):
    video_path = UPLOAD_DIR / video_name
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video '{video_name}' not found.")

    # Pass everything the worker needs to stay decoupled
    background_tasks.add_task(
        extract_frames_task, 
        video_name, 
        UPLOAD_DIR, 
        DATA_DIR, 
        tasks_progress, 
        logger, 
        console
    )
    
    video_id = video_path.stem.replace(" ", "_").lower()
    return {
        "task_id": video_id,
        "message": "Extraction started. Monitor terminal or use /task-status endpoint."
    }

@app.post("/run-colmap/{video_name}")
async def start_colmap_pipeline(video_name: str, background_tasks: BackgroundTasks):
    global is_system_busy
    
    video_id = Path(video_name).stem.replace(" ", "_").lower()
    
    # Lock Check
    if is_system_busy:
        raise HTTPException(status_code=409, detail="System is busy with another task.")

    video_path = UPLOAD_DIR / video_name
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found. Please upload first.")

    # Set Lock
    is_system_busy = True
    
    background_tasks.add_task(
        colmap_pipeline_task,
        video_id,
        DATA_DIR,
        tasks_progress,
        logger
    )

    return {
        "task_id": video_id,
        "message": "COLMAP Pipeline started. System is now locked until completion."
    }


@app.get("/task-status/{video_id}")
async def get_task_status(video_id: str):
    status = tasks_progress.get(video_id.lower())
    if not status:
        raise HTTPException(status_code=404, detail="Task ID not found.")
    return status