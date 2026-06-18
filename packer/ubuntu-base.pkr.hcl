packer {
  required_plugins {
    qemu = {
      source  = "github.com/hashicorp/qemu"
      version = "~> 1"
    }
    ansible = {
      source  = "github.com/hashicorp/ansible"
      version = "~> 1"
    }
  }
}

variable "vm_name" {
  type    = string
  default = "ubuntu-base"
}

variable "cpu" {
  type    = number
  default = 2
}

variable "ram_mb" {
  type    = number
  default = 4096
}

variable "base_image_path" {
  type    = string
  default = "base.img"
}

variable "cloud_init_dir" {
  type    = string
  default = "cloud-init"
}

variable "packages_json" {
  type    = string
  default = "[]"
}

variable "output_dir" {
  type    = string
  default = "output/ubuntu-base"
}

variable "disk_size" {
  type    = string
  default = "20G"
}

source "qemu" "base" {
  iso_url          = var.base_image_path
  iso_checksum     = "none"
  disk_image       = true
  use_backing_file = true

  output_directory = var.output_dir
  vm_name          = "${var.vm_name}.qcow2"
  format           = "qcow2"
  disk_size        = var.disk_size
  disk_interface   = "virtio"
  net_device       = "virtio-net"

  accelerator = "kvm"
  headless    = true

  cpus   = var.cpu
  memory = var.ram_mb

  cd_files = [
    "${var.cloud_init_dir}/user-data",
    "${var.cloud_init_dir}/meta-data"
  ]
  cd_label = "cidata"

  boot_command = []
  boot_wait    = "5s"

  communicator = "ssh"
  ssh_username = "packer"
  ssh_password = "packer"
  ssh_timeout  = "20m"

  shutdown_command = "echo 'packer' | sudo -S shutdown -P now"
}

build {
  sources = ["source.qemu.base"]

  provisioner "shell" {
    inline = ["cloud-init status --wait || true"]
  }

  provisioner "ansible" {
    playbook_file = "ansible/playbooks/base.yml"
    extra_arguments = [
      "--extra-vars", "packages=${var.packages_json}"
    ]
  }
}