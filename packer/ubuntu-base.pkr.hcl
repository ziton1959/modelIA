packer {
  required_plugins {
    qemu = {
      source  = "github.com/hashicorp/qemu"
      version = "~> 1"
    }
  }
}

variable "os_version" {
  default = "22.04.3"
}

variable "vm_name" {
  default = "ubuntu-base"
}

variable "cpu" {
  default = 2
}

variable "ram_mb" {
  default = 4096
}

variable "disk_size" {
  default = "20G"
}

source "qemu" "ubuntu_base" {
  iso_url      = "https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso"
  iso_checksum = "sha256:9bc6028870aef3f74f4e16b900008179e78b130e6b0b9a140635434a46aa98b0"
  output_directory = "output/${var.vm_name}"
  vm_name          = "${var.vm_name}.qcow2"

  cpus        = var.cpu
  memory      = var.ram_mb
  disk_size   = var.disk_size
  format      = "qcow2"
  accelerator = "kvm"

  ssh_username     = "ubuntu"
  ssh_password     = "ubuntu"
  ssh_timeout      = "30m"
  shutdown_command = "echo 'ubuntu' | sudo -S shutdown -P now"

  http_directory = "packer/http"
  boot_wait      = "5s"
  boot_command = [
    "<esc><esc><esc>",
    "<enter><wait>",
    "/casper/vmlinuz ",
    "initrd=/casper/initrd ",
    "autoinstall ",
    "ds=nocloud-net;seedfrom=http://{{ .HTTPIP }}:{{ .HTTPPort }}/",
    "<enter>"
  ]

  headless = true
}

build {
  sources = ["source.qemu.ubuntu_base"]

  provisioner "shell" {
    inline = [
      "sudo apt-get update",
      "sudo apt-get install -y python3 python3-pip"
    ]
  }

  provisioner "ansible" {
    playbook_file = "ansible/playbooks/base.yml"
  }
}
