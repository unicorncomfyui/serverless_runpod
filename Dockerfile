# Multi-stage build for RunPod Serverless ComfyUI with Qwen
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 AS base

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3-pip \
    python3-dev \
    git \
    wget \
    curl \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create symbolic link for python
RUN ln -s /usr/bin/python3.12 /usr/bin/python

# Upgrade pip and install build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install PyTorch with CUDA 12.8 support
RUN pip install --no-cache-dir \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu128

# Install ComfyUI and its dependencies
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/comfyui && \
    cd /app/comfyui && \
    pip install --no-cache-dir -r requirements.txt

# Install Qwen-specific dependencies
RUN pip install --no-cache-dir \
    transformers>=4.37.0 \
    accelerate>=0.25.0 \
    sentencepiece>=0.1.99 \
    tiktoken>=0.5.2 \
    optimum>=1.16.0

# Install custom nodes for Qwen if available
RUN cd /app/comfyui/custom_nodes && \
    echo "Custom nodes will be installed here" && \
    mkdir -p qwen-nodes

# Copy application files
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py /app/
COPY start.sh /app/
COPY workflows/ /app/workflows/
COPY schemas/ /app/schemas/

# Create necessary directories with proper permissions
RUN mkdir -p \
    /app/comfyui/models/checkpoints \
    /app/comfyui/models/upscale_models \
    /app/comfyui/models/embeddings \
    /app/comfyui/models/loras \
    /app/comfyui/models/vae \
    /app/comfyui/output \
    /app/comfyui/input \
    /app/comfyui/temp && \
    chmod -R 777 /app/comfyui/output /app/comfyui/input /app/comfyui/temp

# Make start script executable
RUN chmod +x /app/start.sh

# Expose ComfyUI port
EXPOSE 3000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV COMFYUI_PORT=3000
ENV CUDA_HOME=/usr/local/cuda
ENV PATH="${CUDA_HOME}/bin:${PATH}"
ENV LD_LIBRARY_PATH="${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:3000/ || exit 1

# Start the handler
CMD ["/app/start.sh"]
