FROM ghcr.io/nerfstudio-project/nerfstudio:1.1.3

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 user 2>/dev/null || true && \
    useradd -u 1000 -g 1000 -m -s /bin/bash user 2>/dev/null || true

RUN mkdir -p /home/user/.cache/torch /home/user/.cache/huggingface && \
    chown -R user:user /home/user && \
    mkdir -p /workspace && chown -R user:user /workspace

RUN apt-get update && apt-get install -y python3.10-dev

WORKDIR /workspace/worker

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TORCH_HOME=/home/user/.cache/torch
ENV HF_HOME=/home/user/.cache/huggingface
ENV TORCHINDUCTOR_CACHE_DIR=/home/user/.cache/torchinductor

EXPOSE 8000 7007

USER user

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]