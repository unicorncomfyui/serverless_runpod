#!/bin/bash
set -e

echo "========================================="
echo "ComfyUI Initialization Script"
echo "========================================="

# Clear Triton cache to prevent memory issues after updates
echo "Cleaning Triton cache..."
rm -rf ~/.triton || true
rm -rf /tmp/torchinductor_* || true
rm -rf /tmp/triton_cache_* || true
echo "✓ Triton cache cleared"

# Check if SageAttention is already installed
if python -c "import sageattention" 2>/dev/null; then
    echo "✓ SageAttention already installed, skipping build"
else
    echo "Building SageAttention from source..."
    echo "This will take 2-3 minutes on first run..."

    # Clone and build SageAttention with GPU-optimized compilation
    cd /tmp

    # Remove old clone if exists
    rm -rf SageAttention || true

    # Clone specific commit for stability
    git clone https://github.com/thu-ml/SageAttention.git
    cd SageAttention
    git reset --hard 68de379

    # Build with parallel compilation (matching comfyui-wan settings)
    export EXT_PARALLEL=4
    export NVCC_APPEND_FLAGS="--threads 8"
    export MAX_JOBS=32

    echo "Compiling SageAttention (this may take a few minutes)..."
    pip install -e . > /tmp/sage_build.log 2>&1

    if [ $? -eq 0 ]; then
        echo "✓ SageAttention compilation completed"
        # Clean up build artifacts
        cd /
        rm -rf /tmp/SageAttention

        # Verify installation
        if python -c "import sageattention; print(f'SageAttention version: {sageattention.__version__}')" 2>/dev/null; then
            echo "✓ SageAttention verified and ready"
        else
            echo "❌ CRITICAL: SageAttention built but not importable!"
            echo "This should not happen. Check Python environment."
            exit 1
        fi
    else
        echo "❌ CRITICAL: SageAttention build failed!"
        echo "Build log:"
        cat /tmp/sage_build.log
        echo ""
        echo "This is required for t2v workflows. Exiting."
        exit 1
    fi
fi

# Create text encoder cache directory
mkdir -p /workspace/text_embed_cache
chmod 777 /workspace/text_embed_cache
echo "✓ Text encoder cache directory ready"

# Display CUDA and PyTorch info
echo "========================================="
echo "System Information:"
echo "========================================="
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.version.cuda}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"No GPU\"}')"

echo "========================================="
echo "Initialization complete!"
echo "========================================="
