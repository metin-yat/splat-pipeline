from fastapi import FastAPI
import time

app = FastAPI()

@app.get("/")
async def root():
        return {"status": "healthy", "service": "3dgs-splatting"}



