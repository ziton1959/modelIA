"""
Executor: turns a parsed VM spec into a built image.

Pipeline:
  1. Pick the base image for the requested OS.
  2. Download that golden image from MinIO  (base-images bucket).
  3. Write a cloud-init seed (user-data / meta-data) for SSH login.
  4. Run packer build against packer/ubuntu-base.pkr.hcl, which boots the
     golden image and runs the Ansible playbook to install requested packages.
  5. Upload the resulting qcow2 to MinIO        (vm-images bucket).
  6. Return a result dict consumed by app/routes/vm_create.py.
"""

import os
import json
import shutil
import logging
import subprocess
import tempfile
from pathlib import Path

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
PACKER_TEMPLATE = PROJECT_ROOT / "packer" / "ubuntu-base.pkr.hcl"

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

BASE_BUCKET = os.getenv("MINIO_BASE_BUCKET", "base-images")
BUILT_BUCKET = os.getenv("MINIO_BUILT_BUCKET", "vm-images")

BASE_IMAGE_MAP = {
    "ubuntu 24.04": "ubuntu-24.04.img",
    "ubuntu 22.04": "ubuntu-22.04.img",
    "debian 12":    "debian-12.qcow2",
    "rocky 9":      "Rocky-9.qcow2",
}
DEFAULT_IMAGE = "ubuntu-22.04.img"


def _minio_client():
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def pick_base_image(os_name):
    """Return (image_object_name, matched). matched=False means we fell back."""
    key = (os_name or "").strip().lower()
    if key in BASE_IMAGE_MAP:
        return BASE_IMAGE_MAP[key], True
    return DEFAULT_IMAGE, False


def write_cloud_init(workdir):
    """Write user-data + meta-data so the booted image has an SSH login."""
    ci_dir = workdir / "cloud-init"
    ci_dir.mkdir(parents=True, exist_ok=True)
    (ci_dir / "user-data").write_text(
        "#cloud-config\n"
        "ssh_pwauth: true\n"
        "users:\n"
        "  - name: packer\n"
        "    lock_passwd: false\n"
        "    sudo: ALL=(ALL) NOPASSWD:ALL\n"
        "    shell: /bin/bash\n"
        "    groups: sudo\n"
        "chpasswd:\n"
        "  expire: false\n"
        "  list: |\n"
        "    packer:packer\n"
    )
    (ci_dir / "meta-data").write_text(
        "instance-id: packer-build\n"
        "local-hostname: packer-build\n"
    )
    return ci_dir


def download_base_image(client, object_name, dest):
    client.fget_object(BASE_BUCKET, object_name, str(dest))


def ensure_bucket(client, bucket):
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def run_packer_init():
    try:
        r = subprocess.run(
            ["packer", "init", str(PACKER_TEMPLATE)],
            capture_output=True, text=True, timeout=300,
            cwd=str(PROJECT_ROOT),
        )
        return r.returncode == 0, r.stdout + r.stderr
    except Exception as e:
        return False, "packer init error: " + str(e)


def run_packer_build(spec, base_img, ci_dir, output_dir):
    """Run packer build with -var flags derived from the spec."""
    vm_name = spec.get("template_name", "vm-image")
    cpu = int(spec.get("cpu", 2))
    ram_mb = int(spec.get("ram_gb", 4)) * 1024
    packages_json = json.dumps({"packages": spec.get("packages", [])})
    cmd = [
        "packer", "build", "-force",
        "-var", "vm_name=" + vm_name,
        "-var", "cpu=" + str(cpu),
        "-var", "ram_mb=" + str(ram_mb),
        "-var", "base_image_path=" + str(base_img),
        "-var", "cloud_init_dir=" + str(ci_dir),
        "-var", "packages_json=" + packages_json,
        "-var", "output_dir=" + str(output_dir),
        str(PACKER_TEMPLATE),
    ]
    try:
        env = os.environ.copy()
        env["PACKER_LOG"] = "1"
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=3600,
            cwd=str(PROJECT_ROOT), env=env,
        )
        return r.returncode == 0, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return False, "Packer build timed out after 1 hour"
    except Exception as e:
        return False, "Packer build error: " + str(e)


def upload_built_image(client, output_dir, vm_name):
    qcow2 = output_dir / (vm_name + ".qcow2")
    if not qcow2.exists():
        return False, "expected output not found: " + str(qcow2)
    # Flatten: merge backing file into a standalone image so it's self-contained.
    flat = output_dir / (vm_name + "-flat.qcow2")
    import subprocess
    r = subprocess.run(
        ["qemu-img", "convert", "-O", "qcow2", str(qcow2), str(flat)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return False, "qemu-img convert failed: " + r.stderr
    ensure_bucket(client, BUILT_BUCKET)
    object_name = vm_name + ".qcow2"
    client.fput_object(BUILT_BUCKET, object_name, str(flat))
    return True, BUILT_BUCKET + "/" + object_name



def execute_pipeline(spec):
    """Synchronous pipeline; called via run_in_executor from the route."""
    template_name = spec.get("template_name", "vm-image")
    result = {
        "template_name": template_name,
        "status": "failed",
        "packer_success": False,
        "ansible_success": False,
        "packer_logs": "",
        "ansible_logs": "",
        "error": None,
        "artifact": None,
    }
    workdir = Path(tempfile.mkdtemp(prefix="build-" + template_name + "-"))
    try:
        client = _minio_client()

        object_name, matched = pick_base_image(spec.get("os", ""))
        if not matched:
            result["packer_logs"] += (
                "WARNING: OS '" + str(spec.get("os")) +
                "' not in catalog; falling back to " + object_name + "\n"
            )
        base_img = workdir / object_name
        try:
            download_base_image(client, object_name, base_img)
        except S3Error as e:
            result["error"] = "could not fetch base image " + object_name + ": " + str(e)
            return result
        result["packer_logs"] += "Base image: " + BASE_BUCKET + "/" + object_name + "\n"

        ci_dir = write_cloud_init(workdir)

        ok, init_logs = run_packer_init()
        result["packer_logs"] += "=== INIT ===\n" + init_logs + "\n"
        if not ok:
            result["error"] = "packer init failed"
            return result

        output_dir = workdir / "output"
        ok, build_logs = run_packer_build(spec, base_img, ci_dir, output_dir)
        result["packer_logs"] += "=== BUILD ===\n" + build_logs + "\n"
        result["ansible_logs"] = build_logs
        result["packer_success"] = ok
        result["ansible_success"] = ok
        if not ok:
            result["error"] = "Packer build failed"
            return result

        ok, info = upload_built_image(client, output_dir, template_name)
        if not ok:
            result["error"] = "upload failed: " + info
            return result
        result["artifact"] = info
        result["packer_logs"] += "=== UPLOAD ===\nstored at " + info + "\n"

        result["status"] = "completed"
        return result
    except Exception as e:
        result["error"] = str(e)
        return result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)