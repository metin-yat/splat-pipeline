import subprocess
import httpx
import logging
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import List
from rich.logging import RichHandler

app = FastAPI()

logger = logging.getLogger("SplattingWorker")
logger.setLevel(logging.INFO)
logger.addHandler(RichHandler(rich_tracebacks=True, markup=True))

BACKEND_URL = "http://backend:8000"

class CommandRequest(BaseModel):
    task_id: str
    action: str
    commands: List[str]

@app.get("/")
async def root():
    return {"status": "healthy", "service": "3dgs-splatting"}

@app.post("/execute-task")
async def execute_task(request: CommandRequest, background_tasks: BackgroundTasks):
    logger.info(f"Task received: {request.task_id} — {request.action}")
    background_tasks.add_task(run_pipeline, request.task_id, request.commands)
    return {"status": "accepted", "message": "Pipeline execution started."}

async def run_pipeline(task_id: str, commands: List[str]):
    logger.info(f"Pipeline started: {task_id}")
    status_payload = {"status": "success"}

    try:
        for cmd in commands:
            logger.info(f"Running: {cmd}")
            process = subprocess.Popen(cmd, shell=True, stdout=None, stderr=None)
            process.wait()

            if process.returncode != 0:
                raise Exception(f"Command failed (exit {process.returncode}): {cmd}")

        logger.info(f"Pipeline completed: {task_id}")

    except Exception as e:
        logger.error(f"Pipeline failed: {task_id} — {e}")
        status_payload = {"status": "failed", "error": str(e)}

    finally:
        async with httpx.AsyncClient() as client:
            try:
                await client.patch(f"{BACKEND_URL}/update-task-status/{task_id}", json=status_payload)
                logger.info(f"Callback sent: {task_id}")
            except Exception as cb_err:
                logger.error(f"Callback failed: {cb_err}")