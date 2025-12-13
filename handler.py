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

# Detect ComfyUI directory (same priority as start.sh)
# IMPORTANT: Prioritize container ComfyUI (pinned version) over network volume
if os.path.exists('/app/comfyui'):
    COMFYUI_OUTPUT_DIR = '/app/comfyui/output'
elif os.path.exists('/workspace/ComfyUI'):
    COMFYUI_OUTPUT_DIR = '/workspace/ComfyUI/output'
else:
    COMFYUI_OUTPUT_DIR = '/app/comfyui/output'  # fallback

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


def convert_ui_workflow_to_api(ui_workflow: Dict[str, Any]) -> Dict[str, Any]:
    """Convert ComfyUI UI workflow format to API format"""
    # Check if already in API format (has numeric string keys with class_type)
    if ui_workflow and all(isinstance(k, (int, str)) and isinstance(v, dict) and 'class_type' in v
                           for k, v in list(ui_workflow.items())[:3] if k not in ['extra', 'version']):
        logger.info("Workflow already in API format")
        return ui_workflow

    # UI format detected - convert to API format
    if 'nodes' not in ui_workflow:
        raise ValueError("Invalid workflow: missing 'nodes' array")

    api_workflow = {}

    for node in ui_workflow.get('nodes', []):
        node_id = str(node['id'])

        # Convert inputs from UI format to API format
        api_inputs = {}

        # Get widget values
        if 'widgets_values' in node:
            # Map widgets to their input names based on node type
            for i, value in enumerate(node.get('widgets_values', [])):
                # This is a simplified mapping - may need adjustment per node type
                if i < len(node.get('inputs', [])):
                    input_name = node['inputs'][i].get('name')
                    if input_name:
                        api_inputs[input_name] = value

        # Get connections from inputs
        for inp in node.get('inputs', []):
            if 'link' in inp and inp['link'] is not None:
                # Find the source node/output from links
                link_id = inp['link']
                for link in ui_workflow.get('links', []):
                    if link[0] == link_id:
                        source_node_id = str(link[1])
                        source_output_index = link[2]
                        api_inputs[inp['name']] = [source_node_id, source_output_index]
                        break

        api_workflow[node_id] = {
            "class_type": node['type'],
            "inputs": api_inputs
        }

    logger.info(f"Converted UI workflow to API format ({len(api_workflow)} nodes)")
    return api_workflow


def queue_prompt(workflow: Dict[str, Any]) -> str:
    """Queue a prompt to ComfyUI API and return the prompt_id"""
    try:
        # Convert workflow if needed
        api_workflow = convert_ui_workflow_to_api(workflow)

        response = requests.post(
            f"{BASE_URI}/prompt",
            json={"prompt": api_workflow},
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
                job_history = history[prompt_id]
                logger.info(f"Job {prompt_id} completed")
                logger.info(f"History keys: {list(job_history.keys())}")
                logger.info(f"Full history: {json.dumps(job_history, indent=2)[:1000]}")  # First 1000 chars

                # Check for errors in the history
                if 'status' in job_history:
                    logger.info(f"Job status: {job_history['status']}")

                return job_history

            time.sleep(2)

        except requests.exceptions.RequestException as e:
            logger.warning(f"Error polling for completion: {e}")
            time.sleep(2)


def get_output_files(history: Dict[str, Any]) -> Dict[str, List[str]]:
    """Extract output images and videos from history and encode as base64"""
    images = []
    videos = []
    outputs = history.get('outputs', {})

    logger.info(f"Using ComfyUI output directory: {COMFYUI_OUTPUT_DIR}")
    logger.info(f"History outputs structure: {list(outputs.keys())}")

    for node_id, output in outputs.items():
        logger.info(f"Processing node {node_id}, output keys: {list(output.keys())}")

        # Handle images
        if 'images' in output:
            logger.info(f"Node {node_id} has {len(output['images'])} images")
            for image_info in output['images']:
                filename = image_info.get('filename')
                subfolder = image_info.get('subfolder', '')
                logger.info(f"Image info: filename={filename}, subfolder={subfolder}")

                if filename:
                    image_path = Path(f'{COMFYUI_OUTPUT_DIR}/{subfolder}/{filename}') if subfolder else Path(f'{COMFYUI_OUTPUT_DIR}/{filename}')
                    logger.info(f"Looking for image at: {image_path}")

                    if image_path.exists():
                        logger.info(f"Found image at {image_path}, size: {image_path.stat().st_size} bytes")
                        with open(image_path, 'rb') as img_file:
                            encoded = base64.b64encode(img_file.read()).decode('utf-8')
                            images.append(encoded)

                        # Clean up image file
                        image_path.unlink()
                    else:
                        logger.warning(f"Image not found at {image_path}")
                        # List what's actually in the output directory
                        output_dir = Path(COMFYUI_OUTPUT_DIR)
                        if output_dir.exists():
                            logger.info(f"Contents of {output_dir}: {list(output_dir.glob('**/*'))[:10]}")

        # Handle videos (VHS_VideoCombine outputs - 'gifs' key)
        if 'gifs' in output:
            logger.info(f"Node {node_id} has {len(output['gifs'])} videos (gifs)")
            for video_info in output['gifs']:
                filename = video_info.get('filename')
                subfolder = video_info.get('subfolder', '')
                logger.info(f"Video info: filename={filename}, subfolder={subfolder}")

                if filename:
                    video_path = Path(f'{COMFYUI_OUTPUT_DIR}/{subfolder}/{filename}') if subfolder else Path(f'{COMFYUI_OUTPUT_DIR}/{filename}')
                    logger.info(f"Looking for video at: {video_path}")

                    if video_path.exists():
                        logger.info(f"Found video at {video_path}, size: {video_path.stat().st_size} bytes")
                        with open(video_path, 'rb') as vid_file:
                            encoded = base64.b64encode(vid_file.read()).decode('utf-8')
                            videos.append(encoded)

                        # Clean up video file
                        video_path.unlink()
                    else:
                        logger.warning(f"Video not found at {video_path}")
                        output_dir = Path(COMFYUI_OUTPUT_DIR)
                        if output_dir.exists():
                            logger.info(f"Contents of {output_dir}: {list(output_dir.glob('**/*'))[:10]}")

        # Handle videos (SaveVideo outputs - 'videos' key)
        if 'videos' in output:
            logger.info(f"Node {node_id} has {len(output['videos'])} videos")
            for video_info in output['videos']:
                filename = video_info.get('filename')
                subfolder = video_info.get('subfolder', '')
                logger.info(f"Video info: filename={filename}, subfolder={subfolder}")

                if filename:
                    video_path = Path(f'{COMFYUI_OUTPUT_DIR}/{subfolder}/{filename}') if subfolder else Path(f'{COMFYUI_OUTPUT_DIR}/{filename}')
                    logger.info(f"Looking for video at: {video_path}")

                    if video_path.exists():
                        logger.info(f"Found video at {video_path}, size: {video_path.stat().st_size} bytes")
                        with open(video_path, 'rb') as vid_file:
                            encoded = base64.b64encode(vid_file.read()).decode('utf-8')
                            videos.append(encoded)

                        # Clean up video file
                        video_path.unlink()
                    else:
                        logger.warning(f"Video not found at {video_path}")
                        output_dir = Path(COMFYUI_OUTPUT_DIR)
                        if output_dir.exists():
                            logger.info(f"Contents of {output_dir}: {list(output_dir.glob('**/*'))[:10]}")

    logger.info(f"Retrieved {len(images)} output images and {len(videos)} output videos")
    return {'images': images, 'videos': videos}


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
            workflow_type = 'custom'
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

        # Get output files (images and/or videos)
        output_files = get_output_files(history)

        # Cleanup
        cleanup_models()

        # Return results
        return {
            'images': output_files['images'],
            'videos': output_files['videos'],
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
    logger.info(f"ComfyUI output directory: {COMFYUI_OUTPUT_DIR}")
    runpod.serverless.start({'handler': handler})
