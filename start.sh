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

# Activate virtual environment if it exists
if [ -f "/workspace/venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source /workspace/venv/bin/activate
fi

# Function to check if ComfyUI is ready
wait_for_comfyui() {
    echo "Waiting for ComfyUI to be ready..."
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -s http://127.0.0.1:3000/ > /dev/null 2>&1; then
            echo "ComfyUI is ready!"
            return 0
        fi
        attempt=$((attempt + 1))
        echo "Attempt $attempt/$max_attempts - ComfyUI not ready yet..."
        sleep 2
    done

    echo "ERROR: ComfyUI failed to start within timeout"
    return 1
}

# Determine ComfyUI location
if [ -d "/workspace/ComfyUI" ]; then
    COMFYUI_DIR="/workspace/ComfyUI"
    echo "Using ComfyUI from Network Volume: $COMFYUI_DIR"
elif [ -d "/app/comfyui" ]; then
    COMFYUI_DIR="/app/comfyui"
    echo "Using ComfyUI from container: $COMFYUI_DIR"
else
    echo "ERROR: ComfyUI not found in /workspace/ComfyUI or /app/comfyui"
    exit 1
fi

# Start ComfyUI in the background
echo "Starting ComfyUI server..."
cd "$COMFYUI_DIR"
python main.py --listen 0.0.0.0 --port 3000 --temp-directory /tmp > /workspace/logs/comfyui-serverless.log 2>&1 &
COMFYUI_PID=$!

echo "ComfyUI started with PID: $COMFYUI_PID"

# Wait for ComfyUI to be ready
if ! wait_for_comfyui; then
    echo "ComfyUI logs:"
    cat /workspace/logs/comfyui-serverless.log
    exit 1
fi

# Deactivate venv if it was activated (handler uses its own environment)
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate
fi

# Start the RunPod handler
echo "Starting RunPod handler..."
cd /app
python3 -u handler.py

# If handler exits, kill ComfyUI
kill $COMFYUI_PID 2>/dev/null || true
echo "=== Worker shutdown complete ==="
