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

FAILURE_PROMPT = """You are a helpful DevOps assistant. A VM image build failed.
Read the build log below and explain, in plain language for a non-expert:
1. WHAT went wrong (the specific cause, one or two sentences).
2. HOW to fix it (a concrete, actionable suggestion).

Be concise and friendly. Do NOT output JSON. Do NOT repeat the raw log.
If a package name looks misspelled, point that out and suggest the correct one.
If a repository or network error occurred, say so plainly.

BUILD LOG:
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

SUPPORTED_OS = [
    "Ubuntu 22.04",
    "Ubuntu 24.04",
    "Debian 12",
    "Rocky 9",
]

# Known-good package names (defaults + recipes)
KNOWN_PACKAGES = {
    "docker",
    "docker-ce",
    "docker-compose",
    "python",
    "python3",
    "python3-pip",
    "nginx",
    "nodejs",
    "npm",
    "git",
    "curl",
    "wget",
    "vim",
    "htop",
    "terraform",
    "kubectl",
    "certbot",
}


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
        # Look for a JSON object embedded in the response.
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
            "field": "os",
            "type": "choice",
            "question": "Which operating system would you like?",
            "options": [
                {"label": os, "value": os}
                for os in SUPPORTED_OS
            ],
        })

    if not spec.get("cpu"):
        questions.append({
            "field": "cpu",
            "type": "choice",
            "question": "How many CPU cores?",
            "options": [
                {"label": "1 core", "value": 1},
                {"label": "2 cores", "value": 2},
                {"label": "4 cores", "value": 4},
            ],
        })

    if not spec.get("ram_gb"):
        questions.append({
            "field": "ram_gb",
            "type": "choice",
            "question": "How much RAM?",
            "options": [
                {"label": "2 GB", "value": 2},
                {"label": "4 GB", "value": 4},
                {"label": "8 GB", "value": 8},
            ],
        })

    for pkg in spec.get("packages", []):
        pkg_name = str(pkg).lower()

        if pkg_name in SPECIAL_PACKAGES:
            # Skip if we've already clarified this package.
            if pkg_name in [
                str(c).lower()
                for c in spec.get("_clarified", [])
            ]:
                continue

            sp = SPECIAL_PACKAGES[pkg_name]

            questions.append({
                "field": "pkg_" + pkg_name,
                "type": "package_clarify",
                "package": pkg_name,
                "question": sp["question"],
                "options": sp["options"],
            })

    if not questions and not spec.get("_suggested"):
        existing = [
            str(p).lower()
            for p in spec.get("packages", [])
        ]

        for pkg in spec.get("packages", []):
            sug = SUGGESTIONS.get(str(pkg).lower())

            if sug and sug not in existing:
                questions.append({
                    "field": "packages_extra",
                    "type": "suggest",
                    "question": (
                        "You added " + str(pkg)
                        + ". Would you like " + sug + " too?"
                    ),
                    "options": [
                        {"label": "Yes, add " + sug, "value": sug},
                        {"label": "No thanks", "value": None},
                    ],
                })
                break

    return questions


def finalize_spec(spec):
    """Fill any still-missing fields from admin-configured defaults."""

    if not spec.get("cpu"):
        try:
            spec["cpu"] = int(
                _get_setting("default_cpu", "2")
            )
        except (ValueError, TypeError):
            spec["cpu"] = 2

    if not spec.get("ram_gb"):
        try:
            spec["ram_gb"] = int(
                _get_setting("default_ram_gb", "4")
            )
        except (ValueError, TypeError):
            spec["ram_gb"] = 4

    if not spec.get("os"):
        spec["os"] = _get_setting(
            "default_os",
            "Ubuntu 22.04",
        )

    if not spec.get("template_name"):
        packages_slug = "-".join(
            str(p).lower()
            for p in spec.get("packages", [])
        )

        os_slug = (
            spec["os"]
            .lower()
            .replace(" ", "-")
            .replace(".", "")
        )

        spec["template_name"] = (
            os_slug + "-" + packages_slug
            if packages_slug
            else os_slug
        )

    return spec


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
            # Try to find a close match, e.g. kubrctl -> kubectl.
            match = difflib.get_close_matches(
                p,
                KNOWN_PACKAGES,
                n=1,
                cutoff=0.75,
            )

            if match:
                corrected.append(match[0])
            else:
                unknown.append(p)

    spec["packages"] = corrected

    if unknown:
        spec["_unknown_packages"] = unknown

    return spec


async def parse_vm_request(user_prompt):
    model = _get_setting("active_model", DEFAULT_MODEL)

    # Fixed: this must be a plain URL, not Markdown.
    client = ollama.AsyncClient(
        host="http://127.0.0.1:11434"
    )

    response = await client.generate(
        model=model,
        prompt=SYSTEM_PROMPT + "\n\nUser request: " + user_prompt,
        stream=False,
        format="json",
    )

    raw = response["response"]
    spec = extract_json(raw)

    if spec is None:
        return {
            "error": "failed to parse LLM response",
            "raw": raw,
        }

    if spec.get("status") == "failed":
        return {
            "error": spec.get(
                "error",
                "unsupported request",
            )
        }

    spec = validate_packages(spec)

    return spec


async def explain_failure(logs: str):
    """Ask the model to explain a build failure in plain language."""
    if not logs or not logs.strip():
        return "No log output was captured, so the cause can't be determined. Try rebuilding, or check that the base image and services are available."

    # Extract the most relevant lines: Ansible errors, failed tasks, package errors.
    lines = logs.splitlines()
    relevant = []
    keywords = ("fatal:", "failed!", "no package", "error:", "unable to",
                "could not", "not found", "no matching", "task [", "msg:")
    for line in lines:
        low = line.lower()
        if any(k in low for k in keywords):
            # strip ANSI codes and packer prefixes for clarity
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
            clean = clean.replace("==> qemu.base:", "").strip()
            if clean:
                relevant.append(clean)

    # Build the context: prioritized relevant lines + a bit of the tail as fallback
    if relevant:
        context = "\n".join(relevant[-25:])   # last 25 relevant lines
    else:
        context = logs[-2500:]

    model = _get_setting("active_model", DEFAULT_MODEL)
    client = ollama.AsyncClient(host="http://127.0.0.1:11434")
    try:
        response = await client.generate(
            model=model,
            prompt=FAILURE_PROMPT + context,
            stream=False,
        )
        return response["response"].strip()
    except Exception as e:
        return f"Could not analyze the failure automatically ({e})."