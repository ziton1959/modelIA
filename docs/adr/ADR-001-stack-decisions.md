# ADR-001: Core Stack Decisions

## Status: Accepted

## Packer over Terraform for image creation
Packer is purpose-built for image creation. Terraform manages live infrastructure.
We build images first, deploy later — Packer is the right tool.

## Ansible over Chef/Puppet for configuration
Agentless (SSH only), no server required, YAML-based, huge community.
Works directly on Packer-built images without extra setup.

## Ollama + Llama 3.1 over cloud LLM APIs
Fully local — no data leaves the lab, no API costs, no network dependency.
70B model fits in available RAM (125GB). Quantized (Q4_K_M) if needed.

## Docker Compose over Kubernetes (for now)
Simpler ops for a single-node lab setup. K8s migration planned for M7.

## PostgreSQL over SQLite
Production-grade from day one. SQLite would need migration later anyway.

## MinIO over local filesystem for artifacts
S3-compatible API means zero code changes if we migrate to cloud storage later.
