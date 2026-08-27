import ollama
import json
import re
from typing import Optional

# Fallback if settings can't be read
DEFAULT_MODEL = "llama3.1:8b"

SYSTEM_PROMPT = """You are a VM provisioning assistant for an enterprise platform.

SUPPORTED OPERATING SYSTEMS:
- Ubuntu 22.04
- Ubuntu 24.04
- Debian 12
- Rocky 9

SUPPORTED PACKAGES:
- docker, docker-ce, python, nginx, nodejs, git, curl, wget, vim, htop, terraform, kubectl

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
5. Extract ALL software/tools the user mentions into "packages", even if you're unsure — include terraform, kubectl, docker-ce, etc. Do not drop a requested tool.
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


def _get_setting(key, default):
    """Read a setting, falling back gracefully if the store is unavailable."""
    try:
        from app.core.settings_store import get_setting_sync
        return get_setting_sync(key, default)
    except Exception:
        return default


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
    if not spec or not isinstance(spec, dict):
        return []

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
            # skip if we've already clarified this package
            if str(pkg).lower() in [c.lower() for c in spec.get("_clarified", [])]:
                continue
            sp = SPECIAL_PACKAGES[str(pkg).lower()]
            questions.append({
                "field": "pkg_" + str(pkg).lower(), "type": "package_clarify",
                "package": str(pkg).lower(),
                "question": sp["question"],
                "options": sp["options"],
            })

    if not questions and not spec.get("_suggested"):
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
    # Fill any still-missing fields from admin-configured defaults.
    if not spec.get("cpu"):
        try:
            spec["cpu"] = int(_get_setting("default_cpu", "2"))
        except (ValueError, TypeError):
            spec["cpu"] = 2
    if not spec.get("ram_gb"):
        try:
            spec["ram_gb"] = int(_get_setting("default_ram_gb", "4"))
        except (ValueError, TypeError):
            spec["ram_gb"] = 4
    if not spec.get("os"):
        spec["os"] = _get_setting("default_os", "Ubuntu 22.04")

    if not spec.get("template_name"):
        packages_slug = "-".join(str(p).lower() for p in spec.get("packages", []))
        os_slug = spec["os"].lower().replace(" ", "-").replace(".", "")
        spec["template_name"] = os_slug + "-" + packages_slug if packages_slug else os_slug
    return spec


async def parse_vm_request(user_prompt):
    model = _get_setting("active_model", DEFAULT_MODEL)
    client = ollama.AsyncClient(host="http://127.0.0.1:11434")
    response = await client.generate(
        model=model,
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
    spec = validate_packages(spec)   # ← add this
    return spec

# Known-good package names (defaults + recipes)
KNOWN_PACKAGES = {
    "docker", "docker-ce", "docker-compose", "python", "python3", "python3-pip",
    "nginx", "nodejs", "npm", "git", "curl", "wget", "vim", "htop",
    "terraform", "kubectl", "certbot",
}

def validate_packages(spec):
    """Correct obvious typos and flag unknown packages."""
    import difflib
    corrected = []
    unknown = []
    for pkg in spec.get("packages", []):
        p = str(pkg).lower().strip()
        if p in KNOWN_PACKAGES:
            corrected.append(p)
        else:
            # try to find a close match (catches kubrctl -> kubectl)
            match = difflib.get_close_matches(p, KNOWN_PACKAGES, n=1, cutoff=0.75)
            if match:
                corrected.append(match[0])
            else:
                unknown.append(p)
    spec["packages"] = corrected
    if unknown:
        spec["_unknown_packages"] = unknown
    return spec