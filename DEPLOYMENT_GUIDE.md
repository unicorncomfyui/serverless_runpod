# RunPod Serverless Deployment Guide

This guide walks you through deploying your ComfyUI Qwen Docker image as a RunPod serverless endpoint.

## Prerequisites

- Docker image built and pushed to Docker Hub: `vlop12ui/runpod-comfyui-qwen:latest`
- RunPod account with API key
- Network Volume with models (Qwen, checkpoints, etc.)

## Step 1: Verify Docker Image

First, verify your image is available on Docker Hub:

```bash
# Check the image exists
docker pull vlop12ui/runpod-comfyui-qwen:latest
```

Or visit: https://hub.docker.com/r/vlop12ui/runpod-comfyui-qwen

## Step 2: Create Serverless Endpoint

### Via RunPod Web UI

1. **Navigate to Serverless**
   - Go to https://www.runpod.io/console/serverless
   - Click "New Endpoint"

2. **Configure Endpoint**

   **Basic Settings:**
   - Name: `comfyui-qwen-serverless`
   - Docker Image: `vlop12ui/runpod-comfyui-qwen:latest`

   **GPU Configuration:**
   - GPU Type: RTX 4090 or A100 (recommended)
   - Min Workers: 0 (scale to zero when idle)
   - Max Workers: 3-5 (depending on your needs)
   - Idle Timeout: 5 seconds

   **Container Configuration:**
   - Container Disk: 20 GB (minimum)
   - Expose HTTP Ports: 3000

   **Network Volume:**
   - Attach your Network Volume with models
   - Mount path: `/runpod-volume` (automatic)

   **Environment Variables:**
   ```
   COMFYUI_PORT=3000
   TIMEOUT_SECONDS=600
   MIN_FREE_DISK_GB=0.5
   MIN_FREE_MEMORY_GB=1.0
   ```

3. **Deploy**
   - Click "Deploy"
   - Wait for endpoint to initialize (~2-3 minutes)

### Via RunPod API

```python
import runpod
import os

runpod.api_key = os.getenv("RUNPOD_API_KEY")

endpoint = runpod.create_endpoint(
    name="comfyui-qwen-serverless",
    docker_image="vlop12ui/runpod-comfyui-qwen:latest",
    gpu_ids=["AMPERE_16", "ADA_24"],  # RTX 4090, A100
    network_volume_id="YOUR_VOLUME_ID",
    env={
        "COMFYUI_PORT": "3000",
        "TIMEOUT_SECONDS": "600"
    },
    min_workers=0,
    max_workers=5,
    idle_timeout=5,
    container_disk_in_gb=20
)

print(f"Endpoint ID: {endpoint['id']}")
print(f"Endpoint URL: {endpoint['url']}")
```

## Step 3: Test the Endpoint

### Health Check

```bash
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/health \
  -H "Content-Type: application/json"
```

Expected response:
```json
{
  "status": "healthy",
  "comfyui_status": "running",
  "disk_free_gb": 15.2,
  "memory_free_gb": 22.5
}
```

### Text-to-Image Request (Synchronous)

```python
import runpod
import os

runpod.api_key = os.getenv("RUNPOD_API_KEY")

endpoint = runpod.Endpoint("YOUR_ENDPOINT_ID")

# Run synchronous request
result = endpoint.run_sync(
    {
        "input": {
            "workflow_type": "txt2img",
            "prompt": "A futuristic city at sunset, cyberpunk style, highly detailed",
            "negative_prompt": "blurry, low quality, distorted",
            "width": 1024,
            "height": 1024,
            "steps": 30,
            "cfg_scale": 7.5,
            "seed": 42,
            "checkpoint": "qwen_model.safetensors"
        }
    },
    timeout=600
)

print(f"Status: {result['status']}")
print(f"Images: {len(result['output']['images'])} generated")

# Save images
import base64
for idx, img_base64 in enumerate(result['output']['images']):
    img_data = base64.b64decode(img_base64)
    with open(f"output_{idx}.png", "wb") as f:
        f.write(img_data)
```

### Text-to-Image Request (Asynchronous)

```python
import runpod
import os
import time

runpod.api_key = os.getenv("RUNPOD_API_KEY")

endpoint = runpod.Endpoint("YOUR_ENDPOINT_ID")

# Submit async job
job = endpoint.run(
    {
        "input": {
            "workflow_type": "txt2img",
            "prompt": "A serene mountain landscape with a lake",
            "width": 1024,
            "height": 1024,
            "steps": 30,
            "cfg_scale": 7.5
        }
    }
)

print(f"Job ID: {job.job_id}")
print(f"Status: {job.status()}")

# Poll for completion
while True:
    status = job.status()
    print(f"Status: {status}")

    if status == "COMPLETED":
        result = job.output()
        print(f"Images: {len(result['images'])} generated")
        break
    elif status in ["FAILED", "CANCELLED"]:
        print(f"Job failed: {job.output()}")
        break

    time.sleep(5)
```

### cURL Example

```bash
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_RUNPOD_API_KEY" \
  -d '{
    "input": {
      "workflow_type": "txt2img",
      "prompt": "A beautiful sunset over mountains",
      "width": 1024,
      "height": 1024,
      "steps": 30,
      "cfg_scale": 7.5,
      "seed": 12345
    }
  }'
```

## Step 4: Monitor Performance

### Check Logs

```python
import runpod

endpoint = runpod.Endpoint("YOUR_ENDPOINT_ID")

# Get recent logs
logs = endpoint.get_logs(limit=100)
for log in logs:
    print(f"[{log['timestamp']}] {log['message']}")
```

### Monitor Metrics

Track via RunPod dashboard:
- **Active Workers**: Number of workers currently processing jobs
- **Queue Length**: Number of jobs waiting
- **Average Execution Time**: Time per job
- **GPU Utilization**: GPU usage percentage
- **Cost**: Current spend rate

## Step 5: Troubleshooting

### Issue 1: Endpoint Won't Start

**Symptoms:**
- Workers fail to initialize
- "Container failed to start" error

**Solutions:**
1. Check Docker image exists and is public
2. Verify container disk size is sufficient (min 20 GB)
3. Check logs for startup errors

```bash
# Pull image locally to verify
docker pull vlop12ui/runpod-comfyui-qwen:latest
docker run --rm vlop12ui/runpod-comfyui-qwen:latest /bin/bash -c "python --version"
```

### Issue 2: ComfyUI Not Responding

**Symptoms:**
- Jobs timeout
- "ComfyUI API not accessible" error

**Solutions:**
1. Verify port 3000 is exposed
2. Check ComfyUI startup in logs
3. Increase idle timeout

```python
# Test ComfyUI directly
import requests
response = requests.get("http://localhost:3000/")
print(response.status_code)
```

### Issue 3: Models Not Found

**Symptoms:**
- "Checkpoint not found" error
- "Model file missing" error

**Solutions:**
1. Verify Network Volume is attached
2. Check symlink in logs: `/runpod-volume` → `/workspace`
3. Verify model paths in workflow files

```bash
# Check Network Volume contents
ls -la /runpod-volume/models/checkpoints/
ls -la /workspace/models/checkpoints/
```

### Issue 4: Out of Memory

**Symptoms:**
- "CUDA out of memory" error
- Worker crashes during generation

**Solutions:**
1. Use smaller image dimensions (512x512 instead of 1024x1024)
2. Reduce batch size
3. Use GPU with more VRAM (A100 instead of RTX 4090)
4. Add model offloading in ComfyUI settings

### Issue 5: Slow Cold Starts

**Symptoms:**
- First request takes 2-3 minutes
- Workers take long to initialize

**Solutions:**
1. Set min_workers > 0 to keep workers warm
2. Use smaller Docker image
3. Enable GHA cache in GitHub Actions
4. Pre-load models in Dockerfile

## Performance Benchmarks

### Text-to-Image (1024x1024, 30 steps)

| GPU | Time | Cost/Image | Notes |
|-----|------|------------|-------|
| RTX 4090 | ~8s | $0.04 | Best price/performance |
| A100 (40GB) | ~6s | $0.06 | Faster, higher cost |
| A100 (80GB) | ~6s | $0.08 | For large batches |

### Image-to-Image (1024x1024, 30 steps)

| GPU | Time | Cost/Image | Notes |
|-----|------|------------|-------|
| RTX 4090 | ~10s | $0.05 | Includes image processing |
| A100 (40GB) | ~8s | $0.07 | Faster inference |

## Scaling Recommendations

### Low Traffic (< 100 images/day)
- Min Workers: 0
- Max Workers: 2
- Idle Timeout: 5s
- Estimated Cost: $2-5/day

### Medium Traffic (100-1000 images/day)
- Min Workers: 1
- Max Workers: 5
- Idle Timeout: 30s
- Estimated Cost: $10-30/day

### High Traffic (> 1000 images/day)
- Min Workers: 3
- Max Workers: 10
- Idle Timeout: 60s
- Estimated Cost: $50-100/day

## Next Steps

1. **Optimize Workflows**: Fine-tune ComfyUI workflows for your use case
2. **Add Custom Models**: Upload additional models to Network Volume
3. **Implement Caching**: Cache frequently used models in memory
4. **Set Up Monitoring**: Integrate with logging/monitoring services
5. **Load Testing**: Stress test with concurrent requests

## Useful Commands

```bash
# List endpoints
runpod endpoint list

# Get endpoint details
runpod endpoint get YOUR_ENDPOINT_ID

# Update endpoint config
runpod endpoint update YOUR_ENDPOINT_ID --max-workers 10

# Delete endpoint
runpod endpoint delete YOUR_ENDPOINT_ID

# View real-time logs
runpod endpoint logs YOUR_ENDPOINT_ID --follow
```

## Support Resources

- RunPod Documentation: https://docs.runpod.io/serverless
- ComfyUI Documentation: https://github.com/comfyanonymous/ComfyUI
- GitHub Issues: https://github.com/unicorncomfyui/serverless_runpod/issues
- RunPod Discord: https://discord.gg/runpod

## Additional Configuration

### Custom Workflows

To add new workflows:

1. Create workflow JSON in `workflows/` directory
2. Rebuild Docker image
3. Update `input_schema.json` with new workflow type
4. Update handler to support new workflow

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| COMFYUI_PORT | 3000 | ComfyUI server port |
| TIMEOUT_SECONDS | 600 | Job timeout (10 min) |
| MIN_FREE_DISK_GB | 0.5 | Minimum free disk space |
| MIN_FREE_MEMORY_GB | 1.0 | Minimum free memory |
| DEFAULT_MODEL | - | Default checkpoint model |

### Network Volume Structure

Recommended structure for `/runpod-volume`:

```
/runpod-volume/
├── models/
│   ├── checkpoints/
│   │   ├── qwen_model.safetensors
│   │   └── other_models.safetensors
│   ├── vae/
│   │   └── vae_models.safetensors
│   ├── loras/
│   │   └── lora_models.safetensors
│   ├── embeddings/
│   │   └── embeddings.pt
│   └── upscale_models/
│       └── upscalers.pth
└── ComfyUI/  (optional - if you want to override container ComfyUI)
    ├── custom_nodes/
    └── models/
```

## Conclusion

Your ComfyUI Qwen serverless endpoint is now deployed and ready for production use. The serverless architecture will automatically scale based on demand, keeping costs low during idle periods and handling traffic spikes efficiently.

For questions or issues, please open an issue on GitHub or contact RunPod support.
