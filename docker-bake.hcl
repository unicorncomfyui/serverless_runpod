variable "REGISTRY" {
  default = "docker.io"
}

variable "REGISTRY_USER" {
  default = "vlop12ui"
}

variable "APP" {
  default = "runpod-comfyui-qwen"
}

variable "RELEASE" {
  default = "latest"
}

variable "CU_VERSION" {
  default = "128"
}

target "default" {
  dockerfile = "Dockerfile"
  tags = ["${REGISTRY}/${REGISTRY_USER}/${APP}:${RELEASE}"]
  args = {
    RELEASE = "${RELEASE}"
    INDEX_URL = "https://download.pytorch.org/whl/cu${CU_VERSION}"
    TORCH_VERSION = "2.5.1+cu${CU_VERSION}"
    XFORMERS_VERSION = "0.0.28.post3"
  }
}
