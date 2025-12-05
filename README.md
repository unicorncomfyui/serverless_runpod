# RunPod Serverless ComfyUI avec Qwen

Worker serverless pour RunPod permettant l'exécution de workflows ComfyUI avec support multi-worker.

[![Docker Build](https://github.com/unicorncomfyui/serverless_runpod/actions/workflows/docker-build.yml/badge.svg)](https://github.com/unicorncomfyui/serverless_runpod/actions/workflows/docker-build.yml)

## Table des Matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [Déploiement](#déploiement)
- [Tests](#tests)
- [Workflows](#workflows)

## Vue d'ensemble

Ce projet transforme un template ComfyUI Qwen en worker serverless RunPod avec les caractéristiques suivantes :

- **Multi-worker** : Support de plusieurs workers en parallèle
- **Gestion automatique des ressources** : Vérification mémoire/disque avant traitement
- **Workflows flexibles** : txt2img, img2img, et workflows personnalisés
- **Images Docker optimisées** : CUDA 12.8.1 avec Ubuntu 24.04
- **Nettoyage automatique** : Libération des modèles après traitement

## Architecture

```
serverless_runpod/
├── handler.py              # Handler RunPod principal
├── start.sh                # Script de démarrage
├── Dockerfile              # Image Docker avec CUDA 12.8.1
├── docker-compose.yml      # Pour tests locaux
├── requirements.txt        # Dépendances Python
├── .env.example            # Template de configuration
├── workflows/              # Workflows ComfyUI JSON
│   ├── txt2img.json
│   └── img2img.json
├── schemas/                # Schémas de validation
│   └── input_schema.json
├── models/                 # Modèles (non versionnés)
│   ├── checkpoints/
│   └── upscale_models/
├── input/                  # Images d'entrée pour tests
└── output/                 # Images générées
```

## Prérequis

- Docker avec support GPU (NVIDIA)
- Docker Compose
- Compte RunPod avec API key
- GPU avec CUDA 12.8+ support
- Minimum 8GB VRAM recommandé

## Installation

### 1. Cloner le repo

```bash
git clone <votre-repo>
cd serverless_runpod
git checkout develop
```

### 2. Configuration de l'environnement

```bash
cp .env.example .env
```

Éditez `.env` avec vos paramètres :

```env
RUNPOD_API_KEY=your_api_key_here
COMFYUI_PORT=3000
DEFAULT_MODEL=qwen_model.safetensors
```

### 3. Télécharger les modèles

Placez vos modèles dans :
- `models/checkpoints/` : Modèles principaux (.safetensors, .ckpt)
- `models/upscale_models/` : Modèles d'upscaling (.pth)

```bash
# Exemple avec wget
cd models/checkpoints
wget https://example.com/qwen_model.safetensors

cd ../upscale_models
wget https://example.com/4xLSDIR.pth
```

## Configuration

### Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `RUNPOD_API_KEY` | Clé API RunPod | - |
| `COMFYUI_PORT` | Port ComfyUI | 3000 |
| `TIMEOUT_SECONDS` | Timeout des jobs | 600 |
| `MIN_FREE_DISK_GB` | Espace disque minimum (GB) | 0.5 |
| `MIN_FREE_MEMORY_GB` | Mémoire minimum (GB) | 1.0 |
| `LOG_LEVEL` | Niveau de log | INFO |

## Utilisation

### Test local avec Docker Compose

```bash
# Démarrer le service
docker-compose up --build

# ComfyUI sera accessible sur http://localhost:3000
```

### Tester le handler localement

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer le handler en mode local
python handler.py
```

### Format de requête

```json
{
  "input": {
    "workflow_type": "txt2img",
    "prompt": "beautiful landscape, high quality, detailed",
    "negative_prompt": "blurry, low quality",
    "seed": 42,
    "steps": 20,
    "cfg_scale": 7.0,
    "width": 512,
    "height": 512,
    "sampler_name": "euler",
    "model": "qwen_model.safetensors"
  }
}
```

### Format de réponse

```json
{
  "images": ["base64_encoded_image_1", "base64_encoded_image_2"],
  "prompt_id": "abc123",
  "workflow_type": "txt2img"
}
```

## Déploiement

### 1. Build de l'image Docker

```bash
# Build local
docker build -t your-username/runpod-comfyui-qwen:latest .

# Push vers Docker Hub
docker push your-username/runpod-comfyui-qwen:latest
```

### 2. Créer un endpoint RunPod

Via l'interface RunPod :

1. Allez dans **Serverless** → **New Endpoint**
2. Sélectionnez votre image Docker
3. Configurez :
   - **Container Image** : `your-username/runpod-comfyui-qwen:latest`
   - **GPU Type** : RTX 4090 / A100 (selon budget)
   - **Workers** : Min 0, Max 3-5
   - **Idle Timeout** : 30 secondes
4. Ajoutez les variables d'environnement
5. Déployez

### 3. Tester l'endpoint

```python
import runpod

runpod.api_key = "your_api_key"

endpoint = runpod.Endpoint("your_endpoint_id")

run_request = endpoint.run({
    "workflow_type": "txt2img",
    "prompt": "beautiful landscape",
    "steps": 20
})

# Attendre les résultats
result = run_request.output()
print(result)
```

## Tests

### Tests unitaires

```bash
# Installer les dépendances de test
pip install pytest pytest-asyncio

# Lancer les tests
pytest tests/ -v
```

### Test avec Docker Compose

```bash
# Lancer le service de test
docker-compose --profile test up test-runner
```

## Workflows

### txt2img

Génération d'image à partir de texte.

**Paramètres requis** : `prompt`

**Paramètres optionnels** : `negative_prompt`, `seed`, `steps`, `cfg_scale`, `width`, `height`

### img2img

Transformation d'image existante.

**Paramètres requis** : `prompt`, `input_image` (base64)

**Paramètres optionnels** : `negative_prompt`, `seed`, `steps`, `cfg_scale`, `denoise`

### custom

Workflow personnalisé.

**Paramètres requis** : `custom_workflow` (JSON ComfyUI)

## Troubleshooting

### Problèmes courants

**1. Erreur CUDA out of memory**
```
Solution : Réduire batch_size ou utiliser GPU avec plus de VRAM
```

**2. ComfyUI ne démarre pas**
```bash
# Vérifier les logs
docker-compose logs comfyui-worker

# Vérifier que les modèles sont présents
ls -la models/checkpoints/
```

**3. Timeout sur les jobs**
```
Solution : Augmenter TIMEOUT_SECONDS dans .env
```

### Logs

```bash
# Logs en temps réel
docker-compose logs -f comfyui-worker

# Logs du handler
docker exec -it comfyui-serverless-worker cat /var/log/comfyui.log
```

## Roadmap

- [ ] Support de ControlNet
- [ ] Support de LoRA dynamique
- [ ] Cache des modèles entre workers
- [ ] Métriques et monitoring
- [ ] Support de batch processing
- [ ] Webhooks pour notifications

## Contribution

1. Fork le projet
2. Créez une branche feature (`git checkout -b feature/amazing-feature`)
3. Commit vos changements (`git commit -m 'Add amazing feature'`)
4. Push vers la branche (`git push origin feature/amazing-feature`)
5. Ouvrez une Pull Request

## Licence

Ce projet est sous licence AGPL-3.0 (héritée du template ComfyUI Qwen).

## Support

Pour toute question :
- Ouvrir une issue sur GitHub
- Consulter la documentation RunPod : https://docs.runpod.io/
- Documentation ComfyUI : https://github.com/comfyanonymous/ComfyUI

---

Développé pour RunPod Serverless avec CUDA 12.8.1
