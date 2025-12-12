# Security Policy

## Supported Versions

We release patches for security vulnerabilities. Currently supported versions:

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| develop | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to: [YOUR_SECURITY_EMAIL]

You should receive a response within 48 hours. If for some reason you do not, please follow up via email to ensure we received your original message.

Please include the following information:

- Type of issue (e.g. buffer overflow, SQL injection, cross-site scripting, etc.)
- Full paths of source file(s) related to the manifestation of the issue
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

## Security Best Practices

### For Deployment

1. **API Keys & Secrets**
   - Never commit API keys, tokens, or secrets to the repository
   - Use environment variables for all sensitive data
   - Rotate API keys regularly
   - Use RunPod's secret management for production

2. **Docker Image Security**
   - Images are built from official NVIDIA CUDA base images
   - Regular updates via GitHub Actions on each push
   - Scan images for vulnerabilities before deployment
   - Use specific version tags instead of `latest` in production

3. **Network Security**
   - RunPod serverless endpoints are HTTPS-only by default
   - No exposed ports except the RunPod handler
   - All ComfyUI traffic is internal (localhost only)
   - Use RunPod Network Volumes with proper access controls

4. **Input Validation**
   - All job inputs are validated before processing
   - Resource limits enforced (memory, disk, timeout)
   - Workflow JSON is sanitized before execution
   - No arbitrary code execution from user input

5. **Dependencies**
   - Regularly update Python dependencies
   - Monitor CVEs for dependencies (see below)
   - Pin major versions but allow patch updates
   - Review custom nodes before installation

### Known Security Considerations

#### 1. Custom Nodes
Custom nodes are third-party code that execute in the same environment. Review them before adding:
- Check the repository for suspicious code
- Verify the maintainer's reputation
- Review dependencies and permissions
- Test in isolation before production

#### 2. User-Provided Workflows
Workflows can load arbitrary models and execute node code:
- **Risk**: Malicious workflows could attempt resource exhaustion
- **Mitigation**: Resource limits (timeout, memory, disk checks)
- **Best Practice**: Only accept workflows from trusted sources

#### 3. Model Files
Large model files (`.safetensors`, `.ckpt`) should be vetted:
- **Risk**: Malicious pickle files can execute arbitrary code
- **Mitigation**: Use `.safetensors` format (safe by design)
- **Best Practice**: Only load models from trusted sources (HuggingFace, CivitAI verified)

#### 4. Environment Variables
Sensitive configuration in environment variables:
- **Risk**: Exposure through logs or error messages
- **Mitigation**: Never log full environment, use secrets management
- **Best Practice**: Use RunPod's built-in secrets for API keys

## Dependency Security

### Current Dependencies Status

As of December 2025, the following dependencies are used:

| Package | Minimum Version | Known CVEs |
|---------|----------------|------------|
| runpod | >= 1.5.0 | None known |
| requests | >= 2.31.0 | CVE-2024-35195 (fixed in 2.32.0+) |
| aiohttp | >= 3.9.0 | CVE-2024-23334 (fixed in 3.9.2+) |
| Pillow | >= 10.0.0 | CVE-2023-50447 (fixed in 10.2.0+) |
| python-dotenv | >= 1.0.0 | None known |
| pytest | >= 7.4.0 | None known |

### Recommended Actions

1. **Update dependencies regularly**:
   ```bash
   pip install --upgrade runpod requests aiohttp Pillow
   ```

2. **Use specific versions in production**:
   ```txt
   runpod==1.7.3
   requests==2.32.3
   aiohttp==3.10.5
   Pillow==10.4.0
   python-dotenv==1.0.1
   ```

3. **Automated scanning**:
   - Enable Dependabot on GitHub
   - Use `pip-audit` or `safety` for CVE scanning
   - Run security scans in CI/CD pipeline

## Security Scanning

### Automated Tools

We recommend using the following tools:

1. **GitHub Dependabot**: Automatic dependency updates
2. **pip-audit**: Python dependency CVE scanner
   ```bash
   pip install pip-audit
   pip-audit
   ```

3. **Trivy**: Docker image vulnerability scanner
   ```bash
   trivy image vlop12ui/runpod-comfyui-qwen:latest
   ```

4. **Bandit**: Python code security analyzer
   ```bash
   pip install bandit
   bandit -r handler.py
   ```

### Manual Security Checklist

Before deploying to production:

- [ ] All secrets stored in environment variables or RunPod secrets
- [ ] No API keys or tokens in code or git history
- [ ] Dependencies updated to patch versions
- [ ] Docker image scanned for vulnerabilities
- [ ] Input validation tested with malicious inputs
- [ ] Resource limits tested (memory, disk, timeout)
- [ ] Custom nodes reviewed and tested
- [ ] Network Volume permissions verified
- [ ] Logs reviewed for sensitive data exposure
- [ ] Error messages don't leak internal details

## Incident Response

If a security vulnerability is discovered:

1. **Immediate Actions**:
   - Disable affected endpoints if exploited
   - Rotate any exposed credentials
   - Assess the scope and impact

2. **Investigation**:
   - Review logs for exploitation attempts
   - Identify affected systems/data
   - Document timeline and actions

3. **Remediation**:
   - Apply patches or fixes
   - Test fixes in staging first
   - Deploy to production
   - Monitor for recurrence

4. **Disclosure**:
   - Notify affected users if data was accessed
   - Publish security advisory if appropriate
   - Update documentation

## Security Contacts

- **Security Issues**: [YOUR_SECURITY_EMAIL]
- **General Support**: [GitHub Issues](https://github.com/unicorncomfyui/serverless_runpod/issues)
- **RunPod Support**: https://docs.runpod.io/

## Compliance

This project is designed for:
- **GDPR Compliance**: No user data collected by default
- **SOC 2**: RunPod infrastructure is SOC 2 compliant
- **Data Residency**: Choose RunPod regions based on requirements

---

**Last Updated**: December 2025

This security policy is maintained by the project maintainers and updated regularly.
