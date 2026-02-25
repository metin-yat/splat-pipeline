import cv2
import logging
from pathlib import Path
from rich.progress import (Progress, TextColumn, BarColumn,
            TaskProgressColumn, TimeRemainingColumn)

def extract_frames_task(
    video_name: str, 
    upload_dir: Path, 
    data_dir: Path, 
    tasks_progress: dict, 
    logger: logging.Logger, 
    console, 
    interval_sec: float = 1.0
):
    """
    Worker function to extract frames from a video and save them to the shared data directory.
    """
    video_path = upload_dir / video_name
    video_id = video_path.stem.replace(" ", "_").lower()
    output_dir = data_dir / video_id / "images"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize state
    tasks_progress[video_id] = {"status": "starting", "progress": 0, "saved_frames": 0}
    
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error(f"[bold red]Failed to open video:[/bold red] {video_path}")
        tasks_progress[video_id] = {"status": "failed", "error": "Could not open video"}
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_interval = int(fps * interval_sec)
    
    count = 0
    saved_count = 0

    logger.info(f"[bold cyan]Extraction Started:[/bold cyan] {video_id}")

    # progress Bar setup
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True # Bar disappears from terminal once finished
    ) as progress_bar:
        
        task = progress_bar.add_task(f"[magenta]Processing {video_id}...", total=total_frames)

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if count % frame_interval == 0:
                frame_filename = f"frame_{saved_count:04d}.jpg"
                save_path = output_dir / frame_filename
                
                # High quality save for COLMAP
                cv2.imwrite(str(save_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                saved_count += 1

                # Update shared state for API polling
                current_pct = int((count / total_frames) * 100)
                tasks_progress[video_id].update({
                    "status": "processing",
                    "progress": current_pct, 
                    "saved_frames": saved_count
                })
                
                # Update the animating terminal bar
                progress_bar.update(task, completed=count)

            count += 1

    cap.release()
    tasks_progress[video_id].update({"status": "completed", "progress": 100, "saved_frames": saved_count})
    logger.info(f"[bold green]Finished:[/bold green] {video_id} ({saved_count} frames saved to {output_dir})")