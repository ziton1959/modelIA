# image-factory

An end-to-end DevOps + AI-assisted infrastructure automation platform.

## What it does
A user describes an image in plain English via a web interface.
The AI agent translates that into Packer + Ansible configurations,
builds the image, configures it, and stores the artifact in MinIO.

## Stack
- Packer       — VM image creation
- Ansible      — configuration management
- Docker       — service orchestration
- PostgreSQL   — structured data / metadata
- MinIO        — artifact / object storage
- Llama 3.1    — local AI inference via Ollama

## Structure
packer/       Packer templates and build scripts
ansible/      Roles, playbooks, inventory
docker/       Compose files and service configs
ai-agent/     LLM orchestration and prompt logic
scripts/      Utility and automation scripts
docs/         Architecture decisions and runbooks
tests/        Integration and validation tests
