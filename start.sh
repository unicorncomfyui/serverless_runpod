#!/usr/bin/env bash

echo "=== Starting RunPod Serverless ComfyUI Worker ==="

# Symlink Network Volume to workspace
echo "Symlinking files from Network Volume..."
if [ -d "/runpod-volume" ]; then
    echo "Network Volume detected at /runpod-volume"
    rm -rf /workspace
    ln -s /runpod-volume /workspace
    echo "Symlink created: /workspace -> /runpod-volume"

    # Create logs directory if it doesn't exist
    mkdir -p /workspace/logs
else
    echo "WARNING: No network volume found at /runpod-volume"
    echo "Running without network volume - models must be in container"
    mkdir -p /workspace/logs
fi

# Set environment variables
export PYTHONUNBUFFERED=true
export HF_HOME="/workspace"

# Run initialization script (SageAttention build, Triton cache cleanup)
echo "Running initialization script..."
if [ -f "/app/init.sh" ]; then
    if ! bash /app/init.sh; then
        echo "❌ CRITICAL: Initialization failed!"
        echo "Cannot start ComfyUI without SageAttention."
        echo "Check logs above for details."
        exit 1
    fi
else
    echo "WARNING: init.sh not found, skipping initialization"
fi

# Activate virtual environment if it exists
if [ -f "/workspace/venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source /workspace/venv/bin/activate

    # Ensure pip is accessible and check PyTorch version
    echo "Checking PyTorch installation in venv..."
    python -m pip install --upgrade pip --quiet

    # Check if PyTorch needs CUDA 12.8 upgrade
    TORCH_VERSION=$(python -c "import torch; print(torch.version.cuda if hasattr(torch.version, 'cuda') else 'none')" 2>/dev/null || echo "none")
    if [[ "$TORCH_VERSION" != "12.8"* ]]; then
        echo "Upgrading PyTorch to CUDA 12.8 in venv (current: $TORCH_VERSION)..."
        python -m pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128 --upgrade
    else
        echo "PyTorch CUDA 12.8 already installed, skipping upgrade"
    fi
fi

# Function to check if ComfyUI is ready
wait_for_comfyui() {
    echo "Waiting for ComfyUI to be ready..."
    local max_attempts=90  # Increased from 30 to 90 (3 minutes total)
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -s http://127.0.0.1:3000/ > /dev/null 2>&1; then
            echo "ComfyUI is ready!"
            return 0
        fi
        attempt=$((attempt + 1))

        # Show progress every 10 attempts and tail logs
        if [ $((attempt % 10)) -eq 0 ]; then
            echo "Attempt $attempt/$max_attempts - ComfyUI not ready yet..."
            echo "Last 5 lines from ComfyUI logs:"
            tail -n 5 /workspace/logs/comfyui-serverless.log 2>/dev/null || echo "No logs yet"
        fi

        sleep 2
    done

    echo "ERROR: ComfyUI failed to start within timeout"
    echo "Full ComfyUI logs:"
    cat /workspace/logs/comfyui-serverless.log 2>/dev/null || echo "No logs found"
    return 1
}

# Determine ComfyUI location
# IMPORTANT: Prioritize container ComfyUI (pinned version) over network volume
if [ -d "/app/comfyui" ]; then
    COMFYUI_DIR="/app/comfyui"
    echo "Using ComfyUI from container (pinned version): $COMFYUI_DIR"
elif [ -d "/workspace/ComfyUI" ]; then
    COMFYUI_DIR="/workspace/ComfyUI"
    echo "WARNING: Using ComfyUI from Network Volume: $COMFYUI_DIR"
    echo "This may be outdated. Consider removing /workspace/ComfyUI to use container version."
else
    echo "ERROR: ComfyUI not found in /workspace/ComfyUI or /app/comfyui"
    exit 1
fi

# Check if GPU is available
if nvidia-smi &> /dev/null; then
    echo "✓ GPU detected"
    GPU_ARGS=""
else
    echo "⚠ WARNING: No GPU detected, starting in CPU mode (VERY SLOW)"
    GPU_ARGS="--cpu"
fi

# Start ComfyUI in the background
echo "Starting ComfyUI server..."
echo "ComfyUI directory: $COMFYUI_DIR"
echo "GPU args: $GPU_ARGS"

# Check if main.py exists
if [ ! -f "$COMFYUI_DIR/main.py" ]; then
    echo "ERROR: ComfyUI main.py not found at $COMFYUI_DIR/main.py"
    exit 1
fi

cd "$COMFYUI_DIR"

# Enable tcmalloc for better memory management
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4

python main.py --listen 0.0.0.0 --port 3000 --temp-directory /tmp --use-sage-attention $GPU_ARGS > /workspace/logs/comfyui-serverless.log 2>&1 &
COMFYUI_PID=$!

echo "ComfyUI started with PID: $COMFYUI_PID"
echo "Logs will be written to: /workspace/logs/comfyui-serverless.log"
sleep 3  # Give it a moment to start writing logs
echo "Initial ComfyUI output:"
head -n 20 /workspace/logs/comfyui-serverless.log 2>/dev/null || echo "No logs yet"

# Wait for ComfyUI to be ready
if ! wait_for_comfyui; then
    echo "ComfyUI logs:"
    cat /workspace/logs/comfyui-serverless.log
    exit 1
fi

# Deactivate venv if it was activated (handler uses system Python)
if [ -n "$VIRTUAL_ENV" ]; then
    echo "Deactivating virtual environment: $VIRTUAL_ENV"
    deactivate
fi

# Verify handler dependencies before starting
echo "Verifying handler dependencies..."
python --version
python -m pip list | grep -E "(requests|runpod|aiohttp|Pillow)" || {
    echo "ERROR: Handler dependencies not found. Installing now..."
    python -m pip install --no-cache-dir -r /app/requirements.txt
}

# Start the RunPod handler
echo "Starting RunPod handler..."
cd /app
python -u handler.py

# If handler exits, kill ComfyUI
kill $COMFYUI_PID 2>/dev/null || true
echo "=== Worker shutdown complete ==="
