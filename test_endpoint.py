#!/usr/bin/env python3
"""
Test script for RunPod serverless ComfyUI endpoint
Usage: python test_endpoint.py --endpoint YOUR_ENDPOINT_ID --api-key YOUR_API_KEY
"""

import argparse
import base64
import json
import os
import time
from pathlib import Path
from typing import Dict, Any

try:
    import runpod
except ImportError:
    print("Error: runpod package not installed")
    print("Install with: pip install runpod")
    exit(1)


def save_image(img_base64: str, output_path: str) -> None:
    """Save base64 encoded image to file"""
    img_data = base64.b64decode(img_base64)
    with open(output_path, "wb") as f:
        f.write(img_data)
    print(f"✓ Image saved to: {output_path}")


def test_health_check(endpoint: Any) -> bool:
    """Test endpoint health check"""
    print("\n" + "="*60)
    print("TEST 1: Health Check")
    print("="*60)

    try:
        result = endpoint.health()
        print(f"✓ Health check passed")
        print(f"  Status: {result.get('status', 'unknown')}")
        print(f"  ComfyUI: {result.get('comfyui_status', 'unknown')}")

        if 'disk_free_gb' in result:
            print(f"  Free Disk: {result['disk_free_gb']:.2f} GB")
        if 'memory_free_gb' in result:
            print(f"  Free Memory: {result['memory_free_gb']:.2f} GB")

        return True
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False


def test_txt2img_sync(endpoint: Any, output_dir: Path) -> bool:
    """Test synchronous text-to-image generation"""
    print("\n" + "="*60)
    print("TEST 2: Text-to-Image (Synchronous)")
    print("="*60)

    job_input = {
        "workflow_type": "txt2img",
        "prompt": "A futuristic city at sunset, cyberpunk style, highly detailed, 8k resolution",
        "negative_prompt": "blurry, low quality, distorted, ugly, bad anatomy",
        "width": 512,
        "height": 512,
        "steps": 20,
        "cfg_scale": 7.5,
        "seed": 42,
        "sampler_name": "euler",
        "scheduler": "normal"
    }

    print(f"Prompt: {job_input['prompt'][:60]}...")
    print(f"Size: {job_input['width']}x{job_input['height']}")
    print(f"Steps: {job_input['steps']}")

    try:
        start_time = time.time()
        result = endpoint.run_sync(
            {"input": job_input},
            timeout=600
        )
        elapsed = time.time() - start_time

        print(f"✓ Generation completed in {elapsed:.2f}s")

        if 'output' in result and 'images' in result['output']:
            images = result['output']['images']
            print(f"  Generated {len(images)} image(s)")

            for idx, img_base64 in enumerate(images):
                output_path = output_dir / f"txt2img_sync_{idx}.png"
                save_image(img_base64, str(output_path))

            return True
        else:
            print(f"✗ No images in result: {result}")
            return False

    except Exception as e:
        print(f"✗ Text-to-image failed: {e}")
        return False


def test_txt2img_async(endpoint: Any, output_dir: Path) -> bool:
    """Test asynchronous text-to-image generation"""
    print("\n" + "="*60)
    print("TEST 3: Text-to-Image (Asynchronous)")
    print("="*60)

    job_input = {
        "workflow_type": "txt2img",
        "prompt": "A serene mountain landscape with a crystal clear lake, golden hour lighting",
        "negative_prompt": "blurry, low quality, watermark",
        "width": 512,
        "height": 512,
        "steps": 20,
        "cfg_scale": 7.5,
        "seed": 123
    }

    print(f"Prompt: {job_input['prompt'][:60]}...")

    try:
        # Submit job
        job = endpoint.run({"input": job_input})
        print(f"✓ Job submitted: {job.job_id}")

        # Poll for completion
        start_time = time.time()
        max_wait = 600  # 10 minutes

        while True:
            status = job.status()
            elapsed = time.time() - start_time

            if status == "COMPLETED":
                result = job.output()
                print(f"✓ Job completed in {elapsed:.2f}s")

                if 'images' in result:
                    images = result['images']
                    print(f"  Generated {len(images)} image(s)")

                    for idx, img_base64 in enumerate(images):
                        output_path = output_dir / f"txt2img_async_{idx}.png"
                        save_image(img_base64, str(output_path))

                    return True
                else:
                    print(f"✗ No images in result")
                    return False

            elif status in ["FAILED", "CANCELLED"]:
                print(f"✗ Job {status.lower()}: {job.output()}")
                return False

            elif elapsed > max_wait:
                print(f"✗ Job timed out after {max_wait}s")
                return False

            else:
                print(f"  Status: {status} ({elapsed:.0f}s elapsed)")
                time.sleep(5)

    except Exception as e:
        print(f"✗ Async test failed: {e}")
        return False


def test_img2img(endpoint: Any, output_dir: Path) -> bool:
    """Test image-to-image generation"""
    print("\n" + "="*60)
    print("TEST 4: Image-to-Image")
    print("="*60)

    # Create a simple test image
    try:
        from PIL import Image
        import io

        # Create a simple gradient image
        img = Image.new('RGB', (512, 512))
        pixels = img.load()
        for i in range(512):
            for j in range(512):
                pixels[i, j] = (int(i/2), int(j/2), 128)

        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    except ImportError:
        print("✗ PIL not installed, skipping img2img test")
        print("  Install with: pip install Pillow")
        return False

    job_input = {
        "workflow_type": "img2img",
        "prompt": "A beautiful painted artwork, oil painting style",
        "negative_prompt": "blurry, low quality",
        "image": img_base64,
        "width": 512,
        "height": 512,
        "steps": 20,
        "cfg_scale": 7.5,
        "denoise": 0.7,
        "seed": 456
    }

    print(f"Prompt: {job_input['prompt']}")
    print(f"Denoise: {job_input['denoise']}")

    try:
        start_time = time.time()
        result = endpoint.run_sync(
            {"input": job_input},
            timeout=600
        )
        elapsed = time.time() - start_time

        print(f"✓ Generation completed in {elapsed:.2f}s")

        if 'output' in result and 'images' in result['output']:
            images = result['output']['images']
            print(f"  Generated {len(images)} image(s)")

            for idx, img_base64 in enumerate(images):
                output_path = output_dir / f"img2img_{idx}.png"
                save_image(img_base64, str(output_path))

            return True
        else:
            print(f"✗ No images in result")
            return False

    except Exception as e:
        print(f"✗ Image-to-image failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test RunPod serverless ComfyUI endpoint"
    )
    parser.add_argument(
        "--endpoint",
        required=True,
        help="RunPod endpoint ID"
    )
    parser.add_argument(
        "--api-key",
        help="RunPod API key (or set RUNPOD_API_KEY env var)"
    )
    parser.add_argument(
        "--output-dir",
        default="./test_output",
        help="Directory for output images (default: ./test_output)"
    )
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip health check test"
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip synchronous txt2img test"
    )
    parser.add_argument(
        "--skip-async",
        action="store_true",
        help="Skip asynchronous txt2img test"
    )
    parser.add_argument(
        "--skip-img2img",
        action="store_true",
        help="Skip img2img test"
    )

    args = parser.parse_args()

    # Set API key
    api_key = args.api_key or os.getenv("RUNPOD_API_KEY")
    if not api_key:
        print("Error: RunPod API key not provided")
        print("Set with --api-key or RUNPOD_API_KEY environment variable")
        exit(1)

    runpod.api_key = api_key

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    print(f"Output directory: {output_dir.absolute()}")

    # Initialize endpoint
    print(f"Connecting to endpoint: {args.endpoint}")
    endpoint = runpod.Endpoint(args.endpoint)

    # Run tests
    results = []

    if not args.skip_health:
        results.append(("Health Check", test_health_check(endpoint)))

    if not args.skip_sync:
        results.append(("Text-to-Image (Sync)", test_txt2img_sync(endpoint, output_dir)))

    if not args.skip_async:
        results.append(("Text-to-Image (Async)", test_txt2img_async(endpoint, output_dir)))

    if not args.skip_img2img:
        results.append(("Image-to-Image", test_img2img(endpoint, output_dir)))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        exit(1)


if __name__ == "__main__":
    main()
