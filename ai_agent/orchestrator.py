import ollama
import json
import re
from typing import Optional


MODEL = "llama3.1:70b"

SYSTEM_PROMPT = """You are a VM provisioning assistant for an enterprise platform.
Parse the user's natural language request into a JSON object with exactly these fields:
- os: string (e.g. "Ubuntu 22.04", "CentOS 8")
- cpu: integer (number of CPUs)
- ram_gb: integer (RAM in GB)
- packages: array of strings (software to install)
- template_name: string (slug format, e.g. "ubuntu-docker-nginx")

Respond with valid JSON only. No explanation, no markdown, no code blocks."""


def extract_json(text: str) -> Optional[dict]:
    text = re.sub(r"```json|```", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None


def validate_spec(spec: dict) -> tuple[bool, str]:
    required = ["os", "cpu", "ram_gb", "packages", "template_name"]
    for field in required:
        if field not in spec:
            return False, f"missing field: {field}"
    if not isinstance(spec["cpu"], int) or spec["cpu"] < 1:
        return False, "cpu must be a positive integer"
    if not isinstance(spec["ram_gb"], int) or spec["ram_gb"] < 1:
        return False, "ram_gb must be a positive integer"
    if not isinstance(spec["packages"], list):
        return False, "packages must be an array"
    return True, "ok"


async def parse_vm_request(user_prompt: str) -> dict:
    client = ollama.AsyncClient(host="http://127.0.0.1:11434")

    response = await client.generate(
        model=MODEL,
        prompt=f"{SYSTEM_PROMPT}\n\nUser request: {user_prompt}",
        stream=False
    )

    raw = response["response"]
    spec = extract_json(raw)

    if spec is None:
        return {"error": "failed to parse LLM response", "raw": raw}

    valid, reason = validate_spec(spec)
    if not valid:
        return {"error": f"invalid spec: {reason}", "raw": raw}

    if not spec.get("template_name"):
        packages_slug = "-".join(p.lower() for p in spec["packages"])
        os_slug = spec["os"].lower().replace(" ", "-").replace(".", "")
        spec["template_name"] = f"{os_slug}-{packages_slug}"

    return spec
