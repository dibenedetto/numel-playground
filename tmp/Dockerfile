FROM nvidia/cuda:12.6.2-cudnn-runtime-ubuntu22.04

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    gcc g++ curl wget git \
    python3 python3-pip python3-dev \
    && ln -s /usr/bin/python3 /usr/bin/python \
    && python3 -m pip install --upgrade pip setuptools wheel \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 \
    --index-url https://download.pytorch.org/whl/cu126

ENV PYTHONUNBUFFERED=1
