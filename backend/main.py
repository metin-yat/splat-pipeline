import shutil, re
import logging, os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from fastapi import (FastAPI, UploadFile, File,
                     HTTPException, BackgroundTasks, Query)
from rich.logging import RichHandler
from rich.console import Console
import httpx

from utils import extract_frames_task, colmap_pipeline_task

app = FastAPI()
console = Console()

SPLAT_URL = "http://splat:8000"

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

## Health check of backend and its connection with splatting service
@app.get("/")
async def health_check():
    return {"status": "healthy", "service": "3dgs-backend", "busy": is_system_busy}

@app.get("/test-splatting-service")
async def check_connection_between_services():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{SPLAT_URL}/")
            
        if response.status_code == 200:
            return {
                "status": "success",
                "message": "Splatting works fine!",
                "worker_response": response.json()
            }
        else:
            return {
                "status": "error",
                "message": f"Splatting returned an error: {response.status_code}"
            }
    except Exception as e:
        raise HTTPException(
            status_code=503, 
            detail=f"COULDN2T CONNECT TO SPLATTIN SERVICE. Error: {str(e)}"
        )

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

## endpoints and funcs related to nerfstudio.
@app.patch("/update-task-status/{task_id}")
async def update_task_status(task_id: str, status_payload: dict):
    global is_system_busy
    
    # Update global task status dictionary for the user to query
    tasks_progress[task_id.lower()] = status_payload
    
    if status_payload.get("status") == "success":
        logger.info(f"[bold green]Task {task_id} completed successfully.[/bold green]")
    else:
        logger.error(f"[bold red]Task {task_id} failed:[/bold red] {status_payload.get('error')}")
    
    is_system_busy = False
    return {"message": "System unlocked."}

async def trigger_splatting_task(task_id: str, action: str, commands: list):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # 2. servise liste halinde gönderiyoruz
            payload = {"task_id": task_id, "action": action, "commands": commands}
            await client.post(f"{SPLAT_URL}/execute-task", json=payload)
        except Exception as e:
            global is_system_busy
            is_system_busy = False
            logger.error(f"Failed to trigger Splatting Service: {e}")

@app.post("/start-pipeline/{video_name}")
async def start_pipeline(video_name: str, background_tasks: BackgroundTasks):
    global is_system_busy
    if is_system_busy:
        raise HTTPException(status_code=409, detail="System is busy.")

    video_stem = Path(video_name).stem.replace(" ", "_").lower()
    
    # Process Data that comes from colmap outputs.
    # Generates as [VIDEO_NAME]_final.
    proc_cmd = f"ns-process-data images --data /workspace/data/{video_stem}/images --output-dir /workspace/data/{video_stem}_final --skip-colmap --colmap-model-path /workspace/data/{video_stem}/sparse/0"
    
    # Train command. 
    train_cmd = f"ns-train splatfacto --data /workspace/data/{video_stem}_final/ --output-dir /workspace/data/outputs"
    
    pipeline_commands = [proc_cmd, train_cmd]
    is_system_busy = True
    
    background_tasks.add_task(trigger_splatting_task, video_stem, "full_pipeline", pipeline_commands)
    
    return {
        "message": "Pipeline started successfully.",
        "task_id": video_stem,
        "steps": ["ns-process-data", "ns-train"]
    }

# --- Export and Config Management and Task Status Endpoints
@app.post("/start-export/{video_name}")
async def start_export(video_name: str, background_tasks: BackgroundTasks, config_folder: str = Query(None)):
    global is_system_busy
    if is_system_busy:
        raise HTTPException(status_code=409, detail="System is busy.")

    video_stem = video_name.replace(" ", "_").lower()
    splatfacto_path = DATA_DIR / "outputs" / video_stem / "splatfacto"

    if config_folder:
        selected_config_dir = splatfacto_path / config_folder
    else:
        subdirs = [d for d in splatfacto_path.iterdir() if d.is_dir()]
        if not subdirs:
            raise HTTPException(status_code=404, detail="No training results found.")
        selected_config_dir = max(subdirs, key=os.path.getmtime)

    config_file = selected_config_dir / "config.yml"
    if not config_file.exists():
        raise HTTPException(status_code=404, detail="Config file not found.")

    output_dir = selected_config_dir
    export_cmd = f"ns-export gaussian-splat --load-config {config_file} --output-dir {output_dir}"
    
    # Update progress status for the user
    tasks_progress[video_stem] = {"status": "export_pending", "action": "ns-export"}
    
    is_system_busy = True
    background_tasks.add_task(trigger_splatting_task, video_stem, "export", [export_cmd])
    
    logger.info(f"[bold cyan]Export started:[/bold cyan] {video_stem} -> {output_dir}")
    return {
        "message": "Export task initiated.",
        "task_id": video_stem,
        "export_path": str(output_dir)
    }


@app.get("/list-configs/{video_name}")
async def list_configs(video_name: str):
    video_stem = video_name.replace(" ", "_").lower()
    splatfacto_path = DATA_DIR / "outputs" / video_stem / "splatfacto"
    
    if not splatfacto_path.exists():
        raise HTTPException(status_code=404, detail="Training folder not found.")
    
    # List all date-stamped training folders
    configs = [d.name for d in splatfacto_path.iterdir() if d.is_dir()]
    return {"video_name": video_stem, "available_configs": configs}

@app.get("/task-status/{video_id}")
async def get_task_status(video_id: str):
    status = tasks_progress.get(video_id.lower())
    if not status:
        raise HTTPException(status_code=404, detail="Task ID not found.")
    return status