import ollama
import json
import re
from typing import Optional


MODEL = "llama3.1:70b"

SYSTEM_PROMPT = """You are a VM provisioning assistant for an enterprise platform.

SUPPORTED OPERATING SYSTEMS:
- Ubuntu 22.04
- Ubuntu 24.04
- Debian 12
- Rocky 9

SUPPORTED PACKAGES:
- docker
- python / python3 / python3.12
- nginx
- nodejs / node
- git
- curl
- wget
- vim
- htop

RULES:
1. Respond with VALID JSON ONLY. No explanation, no markdown, no code blocks.

2. If the user requests a SUPPORTED OS and SUPPORTED packages, parse the request into a JSON object with exactly these fields:
   {
     "status": "success",
     "os": "string (e.g. 'Ubuntu 22.04')",
     "cpu": 2,
     "ram_gb": 4,
     "packages": ["array", "of", "strings"],
     "template_name": "string (slug format)"
   }

3. If the user requests an UNSUPPORTED OS (e.g. RedHat, Windows, Fedora, Arch, CentOS), respond with a JSON object containing the expected fields AND the error message:
   {
     "status": "failed",
     "os": "UNSUPPORTED",
     "cpu": 2,
     "ram_gb": 4,
     "packages": [],
     "template_name": "error",
     "error": "UNAVAILABLE: We apologize for the inconvenience, but the operating system '[requested os]' is not currently available. Supported operating systems are: Ubuntu 22.04, Ubuntu 24.04, Debian 12, and Rocky 9."
   }

4. If the user requests an UNSUPPORTED package, respond with a JSON object containing the expected fields AND the error message:
   {
     "status": "failed",
     "os": "SUPPORTED_OS",
     "cpu": 2,
     "ram_gb": 4,
     "packages": [],
     "template_name": "error",
     "error": "UNAVAILABLE: We apologize for the inconvenience, but the package '[package name]' is not currently available. Please choose from our supported packages: docker, python, nginx, nodejs, git, curl, wget, vim, htop."
   }

5. Default values if not specified: cpu=2, ram_gb=4, packages=[]"""


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
    if raw.strip().startswith("UNAVAILABLE:"):
        return {"error": raw.strip()}
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
