# Multi-stage build for RunPod Serverless ComfyUI with Qwen
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 AS base

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Python and pip configuration
ENV PYTHONUNBUFFERED=1 \
    PIP_PREFER_BINARY=1 \
    CMAKE_BUILD_PARALLEL_LEVEL=8

# Set working directory
WORKDIR /app

# Install system dependencies and add deadsnakes PPA for Python 3.11
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3.11-distutils \
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
    libssl-dev \
    libffi-dev \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create symbolic link for python
RUN ln -s /usr/bin/python3.11 /usr/bin/python

# Install pip for Python 3.11
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

# Upgrade pip and install build tools
RUN python -m pip install --upgrade pip setuptools wheel

# Install PyTorch nightly with RTX 5090 support (sm_120, CUDA 12.8)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --pre torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/nightly/cu128 \
    && rm -rf /tmp/* /var/tmp/*

# Install ComfyUI and its dependencies
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/comfyui && \
    cd /app/comfyui && \
    pip install -r requirements.txt \
    && rm -rf /tmp/* /var/tmp/*

# Install Qwen-specific dependencies
RUN pip install \
    transformers>=4.37.0 \
    accelerate>=0.25.0 \
    sentencepiece>=0.1.99 \
    tiktoken>=0.5.2 \
    optimum>=1.16.0 \
    && rm -rf /tmp/* /var/tmp/*

# Install pyOpenSSL and its dependencies (needed for custom nodes like rgthree-comfy)
# Use --ignore-installed to override system cryptography package
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --ignore-installed cryptography>=41.0.0 pyOpenSSL>=23.0.0 \
    && rm -rf /tmp/* /var/tmp/*

# Install opencv-python
RUN pip install opencv-python \
    && rm -rf /tmp/* /var/tmp/*

# Install ComfyUI custom nodes - Batch 1 (lightweight)
RUN cd /app/comfyui/custom_nodes && \
    git clone --depth 1 https://github.com/theUpsider/ComfyUI-Logic.git && \
    git clone --depth 1 https://github.com/chrisgoringe/cg-use-everywhere.git && \
    git clone --depth 1 https://github.com/chrisgoringe/cg-image-picker.git && \
    git clone --depth 1 https://github.com/M1kep/ComfyLiterals.git && \
    git clone --depth 1 https://github.com/Jordach/comfy-plasma.git && \
    git clone --depth 1 https://github.com/ClownsharkBatwing/RES4LYF.git && \
    git clone --depth 1 https://github.com/JPS-GER/ComfyUI_JPS-Nodes.git && \
    rm -rf /tmp/* /var/tmp/*

# Install ComfyUI custom nodes - Batch 2 (medium)
RUN cd /app/comfyui/custom_nodes && \
    git clone --depth 1 https://github.com/rgthree/rgthree-comfy.git && \
    git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes.git && \
    git clone --depth 1 https://github.com/cubiq/ComfyUI_essentials.git && \
    git clone --depth 1 https://github.com/Jonseed/ComfyUI-Detail-Daemon.git && \
    git clone --depth 1 https://github.com/bash-j/mikey_nodes.git && \
    rm -rf /tmp/* /var/tmp/*

# Install ComfyUI custom nodes - Batch 3 (heavy, without models download)
RUN cd /app/comfyui/custom_nodes && \
    git clone --depth 1 --recursive https://github.com/ssitu/ComfyUI_UltimateSDUpscale.git && \
    git clone --depth 1 https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes.git && \
    git clone --depth 1 https://github.com/WASasquatch/was-node-suite-comfyui.git && \
    git clone --depth 1 https://github.com/yolain/ComfyUI-Easy-Use.git && \
    git clone --depth 1 https://github.com/chflame163/ComfyUI_LayerStyle.git && \
    git clone --depth 1 https://github.com/chflame163/ComfyUI_LayerStyle_Advance.git && \
    git clone --depth 1 https://github.com/shadowcz007/comfyui-mixlab-nodes.git && \
    rm -rf /tmp/* /var/tmp/*

# Install ComfyUI custom nodes - Batch 4 (Impact Pack - downloads models)
# Skip model downloads by setting environment variable
RUN cd /app/comfyui/custom_nodes && \
    export SKIP_MODEL_DOWNLOAD=1 && \
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git && \
    rm -rf /tmp/* /var/tmp/*

# Install requirements for ALL custom nodes in one layer (faster build)
RUN --mount=type=cache,target=/root/.cache/pip \
    for dir in /app/comfyui/custom_nodes/*; do \
        if [ -f "$dir/requirements.txt" ]; then \
            echo "Installing requirements for $(basename $dir)..."; \
            pip install -r "$dir/requirements.txt" || true; \
        fi; \
        if [ -f "$dir/install.py" ]; then \
            echo "Running install.py for $(basename $dir)..."; \
            cd "$dir" && python install.py || true; \
        fi; \
    done \
    && rm -rf /tmp/* /var/tmp/* \
    && find /app/comfyui/custom_nodes -name "*.pth" -size +100M -delete \
    && find /app/comfyui/custom_nodes -name "*.safetensors" -size +100M -delete

# Copy application files and install handler dependencies
# Install AFTER custom nodes to ensure dependencies are not removed
COPY requirements.txt /app/
RUN python -m pip install --no-cache-dir -r /app/requirements.txt \
    && python -m pip list | grep -E "(requests|runpod|aiohttp|Pillow)" \
    && rm -rf /tmp/* /var/tmp/*

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

# Health check - Disabled temporarily for debugging
# HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
#     CMD curl -f http://localhost:3000/ || exit 1

# Start the handler
CMD ["/app/start.sh"]
