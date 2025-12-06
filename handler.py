"""
RunPod Serverless Handler for ComfyUI with Qwen Integration
Handles serverless job processing with multi-worker support
"""

import os
import json
import time
import base64
import logging
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional
import runpod

# Configuration
BASE_URI = os.environ.get('COMFYUI_HOST', 'http://127.0.0.1:3000')
TIMEOUT = int(os.environ.get('TIMEOUT_SECONDS', 600))
DISK_MIN_FREE_BYTES = int(float(os.environ.get('MIN_FREE_DISK_GB', 0.5)) * 1024 * 1024 * 1024)
MEMORY_MIN_FREE_BYTES = int(float(os.environ.get('MIN_FREE_MEMORY_GB', 1.0)) * 1024 * 1024 * 1024)

# Setup logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_container_memory_info() -> Dict[str, int]:
    """Get container memory information from cgroup (supports v1 and v2)"""
    try:
        # Try cgroups v2 first (RunPod uses this)
        if os.path.exists('/sys/fs/cgroup/memory.max'):
            with open('/sys/fs/cgroup/memory.max', 'r') as f:
                limit_str = f.read().strip()
                limit = int(limit_str) if limit_str != 'max' else 0
            with open('/sys/fs/cgroup/memory.current', 'r') as f:
                usage = int(f.read().strip())
        # Fallback to cgroups v1
        elif os.path.exists('/sys/fs/cgroup/memory/memory.limit_in_bytes'):
            with open('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'r') as f:
                limit = int(f.read().strip())
            with open('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'r') as f:
                usage = int(f.read().strip())
        else:
            # No cgroups, use psutil or return large values to pass checks
            logger.warning("No cgroup memory info available, assuming sufficient memory")
            return {'limit': 200 * 1024**3, 'usage': 0, 'available': 200 * 1024**3}

        available = limit - usage if limit > 0 else 200 * 1024**3
        return {
            'limit': limit,
            'usage': usage,
            'available': available
        }
    except Exception as e:
        logger.warning(f"Could not read memory info: {e}")
        # Return large values to pass resource checks
        return {'limit': 200 * 1024**3, 'usage': 0, 'available': 200 * 1024**3}


def get_container_disk_info() -> Dict[str, int]:
    """Get disk space information"""
    try:
        import shutil
        stat = shutil.disk_usage('/')
        return {
            'total': stat.total,
            'used': stat.used,
            'free': stat.free
        }
    except Exception as e:
        logger.warning(f"Could not read disk info: {e}")
        return {'total': 0, 'used': 0, 'free': 0}


def check_resources() -> Dict[str, bool]:
    """Check if system has enough resources"""
    memory_info = get_container_memory_info()
    disk_info = get_container_disk_info()

    checks = {
        'memory_ok': memory_info['available'] >= MEMORY_MIN_FREE_BYTES,
        'disk_ok': disk_info['free'] >= DISK_MIN_FREE_BYTES,
        'memory_available_gb': round(memory_info['available'] / (1024**3), 2),
        'disk_free_gb': round(disk_info['free'] / (1024**3), 2)
    }

    logger.info(f"Resource check: {checks}")
    return checks


def validate_input(job_input: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and sanitize input

    Supports two input modes:
    1. Pre-defined workflow: {"workflow_type": "txt2img", "prompt": "...", ...}
    2. Custom workflow: {"workflow": {...ComfyUI workflow JSON...}}
    """
    # Check if custom workflow is provided
    if 'workflow' in job_input:
        # Custom workflow mode - workflow JSON provided directly
        if not isinstance(job_input['workflow'], dict):
            raise ValueError("'workflow' must be a valid ComfyUI workflow JSON object")
        logger.info("Using custom workflow from input")
        return job_input

    # Pre-defined workflow mode - requires workflow_type
    if 'workflow_type' not in job_input:
        raise ValueError("Missing required field: 'workflow_type' or 'workflow'")

    workflow_type = job_input['workflow_type']
    valid_types = ['txt2img', 'img2img']

    if workflow_type not in valid_types:
        raise ValueError(f"Invalid workflow_type. Must be one of: {valid_types}")

    return job_input


def load_workflow(workflow_type: str) -> Dict[str, Any]:
    """Load workflow JSON from file"""
    workflow_path = Path(f'/app/workflows/{workflow_type}.json')

    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow not found: {workflow_path}")

    with open(workflow_path, 'r') as f:
        workflow = json.load(f)

    logger.info(f"Loaded workflow: {workflow_type}")
    return workflow


def inject_parameters(workflow: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """Inject user parameters into workflow"""
    # This is a simplified version - you'll need to adapt based on your workflow structure
    # Typically you'll modify specific nodes in the workflow JSON

    if 'seed' in params:
        # Find KSampler node and update seed
        for node_id, node in workflow.items():
            if isinstance(node, dict) and node.get('class_type') == 'KSampler':
                node['inputs']['seed'] = params['seed']

    if 'prompt' in params:
        # Find CLIPTextEncode node for positive prompt
        for node_id, node in workflow.items():
            if isinstance(node, dict) and node.get('class_type') == 'CLIPTextEncode':
                if 'positive' in node.get('_meta', {}).get('title', '').lower():
                    node['inputs']['text'] = params['prompt']

    if 'negative_prompt' in params:
        # Find CLIPTextEncode node for negative prompt
        for node_id, node in workflow.items():
            if isinstance(node, dict) and node.get('class_type') == 'CLIPTextEncode':
                if 'negative' in node.get('_meta', {}).get('title', '').lower():
                    node['inputs']['text'] = params['negative_prompt']

    logger.info("Injected parameters into workflow")
    return workflow


def queue_prompt(workflow: Dict[str, Any]) -> str:
    """Queue a prompt to ComfyUI API and return the prompt_id"""
    try:
        response = requests.post(
            f"{BASE_URI}/prompt",
            json={"prompt": workflow},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        result = response.json()
        prompt_id = result.get('prompt_id')

        if not prompt_id:
            raise ValueError("No prompt_id returned from ComfyUI")

        logger.info(f"Queued prompt with ID: {prompt_id}")
        return prompt_id

    except requests.exceptions.RequestException as e:
        logger.error(f"Error queuing prompt: {e}")
        raise


def poll_for_completion(prompt_id: str, timeout: int = TIMEOUT) -> Dict[str, Any]:
    """Poll ComfyUI for job completion"""
    start_time = time.time()

    while True:
        if time.time() - start_time > timeout:
            raise TimeoutError(f"Job timed out after {timeout} seconds")

        try:
            response = requests.get(f"{BASE_URI}/history/{prompt_id}", timeout=30)
            response.raise_for_status()
            history = response.json()

            if prompt_id in history:
                logger.info(f"Job {prompt_id} completed")
                return history[prompt_id]

            time.sleep(2)

        except requests.exceptions.RequestException as e:
            logger.warning(f"Error polling for completion: {e}")
            time.sleep(2)


def get_output_images(history: Dict[str, Any]) -> List[str]:
    """Extract output images from history and encode as base64"""
    images = []
    outputs = history.get('outputs', {})

    for node_id, output in outputs.items():
        if 'images' in output:
            for image_info in output['images']:
                filename = image_info.get('filename')
                subfolder = image_info.get('subfolder', '')

                if filename:
                    image_path = Path(f'/app/comfyui/output/{subfolder}/{filename}') if subfolder else Path(f'/app/comfyui/output/{filename}')

                    if image_path.exists():
                        with open(image_path, 'rb') as img_file:
                            encoded = base64.b64encode(img_file.read()).decode('utf-8')
                            images.append(encoded)

                        # Clean up image file
                        image_path.unlink()

    logger.info(f"Retrieved {len(images)} output images")
    return images


def cleanup_models():
    """Unload models to free memory"""
    try:
        response = requests.post(f"{BASE_URI}/free", json={"unload_models": True}, timeout=30)
        response.raise_for_status()
        logger.info("Models unloaded successfully")
    except Exception as e:
        logger.warning(f"Error unloading models: {e}")


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main RunPod serverless handler

    Args:
        event: Job input containing workflow_type and parameters

    Returns:
        Dictionary with images or error information
    """
    try:
        logger.info(f"Processing job with input: {event.get('input', {})}")

        # Check resources
        resources = check_resources()
        if not resources['memory_ok']:
            return {
                'error': f"Insufficient memory. Available: {resources['memory_available_gb']}GB"
            }
        if not resources['disk_ok']:
            return {
                'error': f"Insufficient disk space. Available: {resources['disk_free_gb']}GB"
            }

        # Validate input
        job_input = validate_input(event.get('input', {}))

        # Get workflow (either from file or from input)
        if 'workflow' in job_input:
            # Custom workflow provided directly
            workflow = job_input['workflow']
            logger.info("Using custom workflow from input")
        else:
            # Load pre-defined workflow from file
            workflow_type = job_input['workflow_type']
            workflow = load_workflow(workflow_type)
            # Inject user parameters
            workflow = inject_parameters(workflow, job_input)

        # Queue prompt
        prompt_id = queue_prompt(workflow)

        # Wait for completion
        history = poll_for_completion(prompt_id)

        # Get output images
        images = get_output_images(history)

        # Cleanup
        cleanup_models()

        # Return results
        return {
            'images': images,
            'prompt_id': prompt_id,
            'workflow_type': workflow_type
        }

    except Exception as e:
        logger.error(f"Error in handler: {e}", exc_info=True)
        return {
            'error': str(e),
            'error_type': type(e).__name__
        }


if __name__ == '__main__':
    logger.info("Starting RunPod serverless handler...")
    runpod.serverless.start({'handler': handler})
