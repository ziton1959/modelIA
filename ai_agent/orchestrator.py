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
- docker, python, nginx, nodejs, git, curl, wget, vim, htop

RULES:
1. Respond with VALID JSON ONLY. No explanation, no markdown, no code blocks.
2. Parse the request into a JSON object with exactly these fields:
   {
     "status": "success",
     "os": "string or null if the user did NOT specify an OS",
     "cpu": integer or null if NOT specified,
     "ram_gb": integer or null if NOT specified,
     "packages": ["array of package names the user asked for"],
     "mentioned": ["list of which fields the user EXPLICITLY specified"]
   }
3. IMPORTANT: Do NOT invent defaults. If the user did not say an OS, set "os": null. If no CPU, "cpu": null. If no RAM, "ram_gb": null. Only fill fields the user actually mentioned.
4. If the user requests an UNSUPPORTED OS (Windows, Fedora, Arch, CentOS, RedHat), respond:
   {"status": "failed", "error": "UNAVAILABLE: The operating system is not supported. Supported: Ubuntu 22.04, Ubuntu 24.04, Debian 12, Rocky 9."}
"""

SPECIAL_PACKAGES = {
    "terraform": {
        "question": "Terraform isn't in the default repos - it needs HashiCorp's official repository. How should I handle it?",
        "options": [
            {"label": "Set up the official repo", "value": "terraform"},
            {"label": "Skip terraform", "value": None},
        ],
    },
    "kubernetes": {
        "question": "'Kubernetes' can mean different things. What do you need?",
        "options": [
            {"label": "Just kubectl (CLI)", "value": "kubectl"},
            {"label": "Skip for now", "value": None},
        ],
    },
}

SUGGESTIONS = {
    "docker": "docker-compose",
    "python": "python3-pip",
    "nginx": "certbot",
    "nodejs": "npm",
}

SUPPORTED_OS = ["Ubuntu 22.04", "Ubuntu 24.04", "Debian 12", "Rocky 9"]


def extract_json(text):
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


def check_missing(spec):
    questions = []

    if not spec.get("os") or spec.get("os") == "null":
        questions.append({
            "field": "os", "type": "choice",
            "question": "Which operating system would you like?",
            "options": [{"label": os, "value": os} for os in SUPPORTED_OS],
        })

    if not spec.get("cpu"):
        questions.append({
            "field": "cpu", "type": "choice",
            "question": "How many CPU cores?",
            "options": [{"label": "1 core", "value": 1},
                        {"label": "2 cores", "value": 2},
                        {"label": "4 cores", "value": 4}],
        })

    if not spec.get("ram_gb"):
        questions.append({
            "field": "ram_gb", "type": "choice",
            "question": "How much RAM?",
            "options": [{"label": "2 GB", "value": 2},
                        {"label": "4 GB", "value": 4},
                        {"label": "8 GB", "value": 8}],
        })

    for pkg in spec.get("packages", []):
        if str(pkg).lower() in SPECIAL_PACKAGES:
            sp = SPECIAL_PACKAGES[str(pkg).lower()]
            questions.append({
                "field": "pkg_" + str(pkg).lower(), "type": "package_clarify",
                "package": str(pkg).lower(),
                "question": sp["question"],
                "options": sp["options"],
            })

    if not questions:
        existing = [str(p).lower() for p in spec.get("packages", [])]
        for pkg in spec.get("packages", []):
            sug = SUGGESTIONS.get(str(pkg).lower())
            if sug and sug not in existing:
                questions.append({
                    "field": "packages_extra", "type": "suggest",
                    "question": "You added " + str(pkg) + ". Would you like " + sug + " too?",
                    "options": [{"label": "Yes, add " + sug, "value": sug},
                                {"label": "No thanks", "value": None}],
                })
                break

    return questions


def finalize_spec(spec):
    if not spec.get("template_name"):
        packages_slug = "-".join(str(p).lower() for p in spec.get("packages", []))
        os_slug = spec["os"].lower().replace(" ", "-").replace(".", "")
        spec["template_name"] = os_slug + "-" + packages_slug if packages_slug else os_slug
    return spec


async def parse_vm_request(user_prompt):
    client = ollama.AsyncClient(host="http://127.0.0.1:11434")
    response = await client.generate(
        model=MODEL,
        prompt=SYSTEM_PROMPT + "\n\nUser request: " + user_prompt,
        stream=False,
        format="json",
    )
    raw = response["response"]
    spec = extract_json(raw)
    if spec is None:
        return {"error": "failed to parse LLM response", "raw": raw}
    if spec.get("status") == "failed":
        return {"error": spec.get("error", "unsupported request")}
    return spec
