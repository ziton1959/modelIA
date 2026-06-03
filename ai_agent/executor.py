
import subprocess
import json
import os
import tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PACKER_TEMPLATES_DIR = Path(__file__).parent.parent / "packer" / "templates"
ANSIBLE_PLAYBOOKS_DIR = Path(__file__).parent.parent / "ansible" / "playbooks"

# ─── PACKER ───────────────────────────────────────────────────────────────────

def generate_packer_template(spec: dict) -> dict:
    """Generate a Packer HCL2 template from a VM spec."""
    os_name = spec.get("os", "Ubuntu 24.04")
    packages = spec.get("packages", [])
    template_name = spec.get("template_name", "base-image")

    # Map OS name to ISO details
    os_map = {
        "ubuntu 24.04": {
            "iso_url": "https://releases.ubuntu.com/24.04/ubuntu-24.04-live-server-amd64.iso",
            "iso_checksum": "sha256:8762f7e74e4d64d72fceb5f70682e6b069932deedb4949c6975d0f0fe0a91be3",
            "guest_os_type": "Ubuntu_64"
        },
        "ubuntu 22.04": {
            "iso_url": "https://releases.ubuntu.com/22.04/ubuntu-22.04.4-live-server-amd64.iso",
            "iso_checksum": "sha256:45f873de9f8cb637345d6e66a583762730bbea30277ef7b32c9c3bd6700a32b2",
            "guest_os_type": "Ubuntu_64"
        },
    }

    os_key = os_name.lower()
    os_config = os_map.get(os_key, os_map["ubuntu 24.04"])
    packages_install = " ".join(packages)

    packer_spec = {
        "template_name": template_name,
        "os": os_name,
        "iso_url": os_config["iso_url"],
        "iso_checksum": os_config["iso_checksum"],
        "packages": packages,
        "shell_commands": [
            "apt-get update -y",
            f"apt-get install -y {packages_install}" if packages else "echo 'no packages'",
            "apt-get clean"
        ]
    }

    return packer_spec


def write_packer_template(spec: dict, output_dir: Path) -> Path:
    """Write a Packer HCL2 template file to disk."""
    template_name = spec.get("template_name", "base-image")
    packages = spec.get("packages", [])
    packages_install = " ".join(packages)
    iso_url = spec.get("iso_url", "")
    iso_checksum = spec.get("iso_checksum", "")

    hcl_content = f'''
packer {{
  required_plugins {{
    virtualbox = {{
      version = ">= 1.0.0"
      source  = "github.com/hashicorp/virtualbox"
    }}
  }}
}}

variable "template_name" {{
  default = "{template_name}"
}}

source "virtualbox-iso" "base" {{
  vm_name          = "{template_name}"
  iso_url          = "{iso_url}"
  iso_checksum     = "{iso_checksum}"
  disk_size        = 20480
  memory           = {spec.get("ram_gb", 4) * 1024}
  cpus             = {spec.get("cpu", 2)}
  headless         = true
  ssh_username     = "ubuntu"
  ssh_password     = "ubuntu"
  ssh_timeout      = "30m"
  shutdown_command = "echo ubuntu | sudo -S shutdown -P now"
  output_directory = "/tmp/packer-output/{template_name}"
}}

build {{
  sources = ["source.virtualbox-iso.base"]

  provisioner "shell" {{
    inline = [
      "sudo apt-get update -y",
      "sudo apt-get install -y {packages_install}",
      "sudo apt-get clean"
    ]
  }}
}}
'''

    output_dir.mkdir(parents=True, exist_ok=True)
    template_path = output_dir / f"{template_name}.pkr.hcl"
    template_path.write_text(hcl_content)
    return template_path


def run_packer(template_path: Path) -> tuple[bool, str]:
    """Run packer build and return (success, logs)."""
    try:
        env = os.environ.copy()
        env["PACKER_LOG"] = "1"

        result = subprocess.run(
            ["packer", "build", "-force", str(template_path)],
            capture_output=True,
            text=True,
            timeout=3600,
            env=env
        )

        logs = result.stdout + result.stderr
        success = result.returncode == 0
        return success, logs

    except subprocess.TimeoutExpired:
        return False, "Packer build timed out after 1 hour"
    except Exception as e:
        return False, f"Packer error: {str(e)}"


def validate_packer_template(template_path: Path) -> tuple[bool, str]:
    """Run packer validate before building."""
    try:
        result = subprocess.run(
            ["packer", "validate", str(template_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        logs = result.stdout + result.stderr
        return result.returncode == 0, logs
    except Exception as e:
        return False, f"Packer validate error: {str(e)}"


# ─── ANSIBLE ──────────────────────────────────────────────────────────────────

def generate_ansible_playbook(spec: dict) -> dict:
    """Generate Ansible roles list from a VM spec."""
    packages = spec.get("packages", [])
    roles = []

    # Map packages to ansible roles
    package_role_map = {
        "docker": "docker",
        "python3.12": "python",
        "python3": "python",
        "python": "python",
        "nginx": "nginx",
        "git": "base",
        "curl": "base",
        "wget": "base",
    }

    for pkg in packages:
        role = package_role_map.get(pkg.lower())
        if role and role not in roles:
            roles.append(role)

    if "base" not in roles:
        roles.insert(0, "base")

    return {"roles": roles, "packages": packages}


def write_ansible_playbook(spec: dict, output_dir: Path) -> Path:
    """Write an Ansible playbook YAML file to disk."""
    template_name = spec.get("template_name", "base-image")
    ansible_spec = generate_ansible_playbook(spec)
    roles = ansible_spec["roles"]
    packages = ansible_spec["packages"]

    roles_yaml = "\n".join([f"    - {r}" for r in roles])
    packages_yaml = "\n".join([f"    - {p}" for p in packages])

    playbook_content = f"""---
- name: Configure {template_name}
  hosts: all
  become: true
  vars:
    template_name: "{template_name}"
    packages:
{packages_yaml}

  roles:
{roles_yaml}
"""

    output_dir.mkdir(parents=True, exist_ok=True)
    playbook_path = output_dir / f"{template_name}.yml"
    playbook_path.write_text(playbook_content)
    return playbook_path


def run_ansible(playbook_path: Path, inventory: str = "localhost,") -> tuple[bool, str]:
    """Run ansible-playbook and return (success, logs)."""
    try:
        result = subprocess.run(
            [
                "ansible-playbook",
                str(playbook_path),
                "-i", inventory,
                "--connection=local",
                "-v"
            ],
            capture_output=True,
            text=True,
            timeout=1800,
        )

        logs = result.stdout + result.stderr
        success = result.returncode == 0
        return success, logs

    except subprocess.TimeoutExpired:
        return False, "Ansible timed out after 30 minutes"
    except Exception as e:
        return False, f"Ansible error: {str(e)}"


# ─── FULL PIPELINE ────────────────────────────────────────────────────────────

def execute_pipeline(spec: dict) -> dict:
    """
    Full execution pipeline:
    1. Generate + validate Packer template
    2. Run Packer build
    3. Generate + run Ansible playbook
    Returns a result dict with status and logs.
    """
    template_name = spec.get("template_name", "base-image")
    result = {
        "template_name": template_name,
        "packer_validated": False,
        "packer_success": False,
        "ansible_success": False,
        "packer_logs": "",
        "ansible_logs": "",
        "error": None
    }

    try:
        # Step 1 — generate packer spec
        packer_spec = generate_packer_template(spec)
        result["packer_spec"] = packer_spec

        # Step 2 — write packer template
        packer_path = write_packer_template(
            {**spec, **packer_spec},
            PACKER_TEMPLATES_DIR
        )
        logger.info(f"Packer template written: {packer_path}")

        # Step 3 — validate packer template
        valid, validate_logs = validate_packer_template(packer_path)
        result["packer_validated"] = valid
        result["packer_logs"] += f"=== VALIDATE ===\n{validate_logs}\n"

        if not valid:
            result["error"] = "Packer template validation failed"
            return result

        # Step 4 — run packer build
        success, build_logs = run_packer(packer_path)
        result["packer_success"] = success
        result["packer_logs"] += f"=== BUILD ===\n{build_logs}\n"

        if not success:
            result["error"] = "Packer build failed"
            return result

        # Step 5 — generate ansible roles
        ansible_spec = generate_ansible_playbook(spec)
        result["ansible_roles"] = ansible_spec["roles"]

        # Step 6 — write ansible playbook
        playbook_path = write_ansible_playbook(
            spec,
            ANSIBLE_PLAYBOOKS_DIR
        )
        logger.info(f"Ansible playbook written: {playbook_path}")

        # Step 7 — run ansible
        ansible_success, ansible_logs = run_ansible(playbook_path)
        result["ansible_success"] = ansible_success
        result["ansible_logs"] = ansible_logs

        if not ansible_success:
            result["error"] = "Ansible configuration failed"
            return result

        result["status"] = "completed"
        return result

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "failed"
        return result