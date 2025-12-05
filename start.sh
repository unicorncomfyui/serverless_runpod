#!/bin/bash
set -e

echo "=== Starting RunPod Serverless ComfyUI Worker ==="

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

# Start ComfyUI in the background
echo "Starting ComfyUI server..."
cd /app/comfyui
python main.py --listen 0.0.0.0 --port 3000 > /var/log/comfyui.log 2>&1 &
COMFYUI_PID=$!

echo "ComfyUI started with PID: $COMFYUI_PID"

# Wait for ComfyUI to be ready
if ! wait_for_comfyui; then
    echo "ComfyUI logs:"
    cat /var/log/comfyui.log
    exit 1
fi

# Start the RunPod handler
echo "Starting RunPod handler..."
cd /app
python -u handler.py

# If handler exits, kill ComfyUI
kill $COMFYUI_PID 2>/dev/null || true
echo "=== Worker shutdown complete ==="
