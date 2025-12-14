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

# SageAttention installation with network volume caching
# Cache is validated against commit hash to ensure correctness
SAGE_CACHE_DIR="/workspace/sageattention_cache"
SAGE_COMMIT="68de379"
SAGE_COMMIT_FILE="$SAGE_CACHE_DIR/.commit_hash"

# Function to compile SageAttention from source
compile_sageattention() {
    echo "Building SageAttention from source (commit $SAGE_COMMIT)..."
    echo "This will take 2-3 minutes..."

    cd /tmp
    rm -rf SageAttention || true

    git clone https://github.com/thu-ml/SageAttention.git
    cd SageAttention
    git reset --hard $SAGE_COMMIT

    # Build with parallel compilation (matching comfyui-wan settings)
    export EXT_PARALLEL=4
    export NVCC_APPEND_FLAGS="--threads 8"
    export MAX_JOBS=32

    echo "Compiling SageAttention..."
    pip install -e . > /tmp/sage_build.log 2>&1

    if [ $? -eq 0 ]; then
        if python -c "import sageattention; print(f'SageAttention {sageattention.__version__} compiled')" 2>/dev/null; then
            echo "✓ SageAttention compilation successful"

            # Cache the build on network volume for future cold starts
            echo "Caching compiled build to network volume..."
            mkdir -p "$SAGE_CACHE_DIR"
            rm -rf "$SAGE_CACHE_DIR/SageAttention" || true
            cp -r /tmp/SageAttention "$SAGE_CACHE_DIR/SageAttention"
            echo "$SAGE_COMMIT" > "$SAGE_COMMIT_FILE"
            echo "✓ Build cached (future cold starts will be ~10s instead of 2-3min)"

            cd /
            rm -rf /tmp/SageAttention
            return 0
        else
            echo "❌ CRITICAL: SageAttention built but not importable!"
            cd /
            rm -rf /tmp/SageAttention
            return 1
        fi
    else
        echo "❌ CRITICAL: SageAttention build failed!"
        echo "Build log:"
        cat /tmp/sage_build.log
        echo ""
        cd /
        rm -rf /tmp/SageAttention
        return 1
    fi
}

# Check if SageAttention is already installed in current container
if python -c "import sageattention" 2>/dev/null; then
    echo "✓ SageAttention already installed in container"
else
    # Check if we have a cached build
    if [ -d "$SAGE_CACHE_DIR/SageAttention" ] && [ -f "$SAGE_COMMIT_FILE" ]; then
        CACHED_COMMIT=$(cat "$SAGE_COMMIT_FILE")

        if [ "$CACHED_COMMIT" = "$SAGE_COMMIT" ]; then
            echo "Found cached SageAttention build (commit $SAGE_COMMIT)"
            echo "Installing from cache (~10 seconds)..."

            cd "$SAGE_CACHE_DIR/SageAttention"
            pip install -e . > /tmp/sage_cache_install.log 2>&1

            if python -c "import sageattention; print(f'SageAttention {sageattention.__version__} from cache')" 2>/dev/null; then
                echo "✓ SageAttention restored from cache successfully"
            else
                echo "⚠️  Cached build failed to import, rebuilding from source..."
                rm -rf "$SAGE_CACHE_DIR/SageAttention"
                rm -f "$SAGE_COMMIT_FILE"
                compile_sageattention || exit 1
            fi
        else
            echo "⚠️  Cached build is outdated (cached: $CACHED_COMMIT, needed: $SAGE_COMMIT)"
            echo "Removing old cache and rebuilding..."
            rm -rf "$SAGE_CACHE_DIR/SageAttention"
            rm -f "$SAGE_COMMIT_FILE"
            compile_sageattention || exit 1
        fi
    else
        # No cache, compile from source
        echo "No cached build found, compiling from source..."
        compile_sageattention || exit 1
    fi
fi

# Final verification before starting ComfyUI
if ! python -c "import sageattention" 2>/dev/null; then
    echo "❌ CRITICAL: SageAttention not available after installation!"
    echo "Cannot start ComfyUI without SageAttention."
    exit 1
fi

echo "✓ SageAttention ready"

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
