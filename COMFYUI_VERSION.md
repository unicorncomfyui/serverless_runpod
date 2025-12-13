# ComfyUI Version Management

## Current Version

**Commit**: `36357bbcc3c515e37a742457a2b2ab4b7ccc17a8`
**Date**: December 10, 2025
**Status**: ✅ Verified working (from production build)
**Message**: "process the NodeV1 dict results correctly (#11237)"

## Why Pin the Version?

Without pinning, each Docker rebuild pulls the latest ComfyUI commit, which can introduce bugs or breaking changes.

By fixing the commit hash, you ensure:
- ✅ Reproducible builds every time
- ✅ No surprises during rebuilds
- ✅ Full control over when to update

## How to Update ComfyUI

### 1. Check for new commits

Visit https://github.com/comfyanonymous/ComfyUI/commits/master

### 2. Choose a commit

Select a stable commit and copy its full hash (40 characters)

### 3. Test locally (recommended)

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
git checkout <NEW_COMMIT_HASH>
python main.py --listen 0.0.0.0
```

Test your workflows (text-to-image, image-to-video) before deploying.

### 4. Update the Dockerfile

Edit line 70 in `Dockerfile`:

```dockerfile
git checkout <NEW_COMMIT_HASH> && \
```

Update line 66 comment with the new date.

### 5. Rebuild and deploy

```bash
# Local rebuild
docker build -t comfyui-serverless:test .

# Or push to develop - GitHub Actions builds automatically
git commit -am "Update ComfyUI to <SHORT_HASH>"
git push origin develop
```

## Rollback Procedure

If an update breaks something:

```bash
git revert HEAD
git push origin develop
```

Or manually restore the previous commit hash in the Dockerfile.

## Update Checklist

When updating ComfyUI, verify:

- ⚠️ **CUDA compatibility**: Must not require CUDA >12.8 (RunPod limitation)
- ⚠️ **Custom nodes**: Check compatibility with 21 installed custom nodes
- ⚠️ **Model formats**: New safetensors formats may need handler changes
- ⚠️ **API compatibility**: Ensure handler.py still works with new ComfyUI API
- ⚠️ **Workflows**: Test both Z-Image Turbo (t2i) and WAN 2.2 (i2v) workflows

## Version History

| Commit Hash | Date | Status | Notes |
|------------|------|--------|-------|
| `36357bbc` | 2025-12-10 | ✅ Current | NodeV1 dict processing, CUDA 12.8.1 compatible |
