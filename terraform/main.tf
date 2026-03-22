terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "0.7.6"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0"
    }
  }
}

provider "libvirt" {
  uri = "qemu:///system"
}

# ── Variables ──────────────────────────────────────────────────────────────────
variable "deploy" {
  description = "Which image to deploy: standard, lvm, boot-menu"
  type        = string
}

variable "ssh_pub_key_path" {
  description = "Path to the SSH public key (lab_key.pub) to inject into the VM at apply time"
  type        = string
  default     = "~/.ssh/lab_key.pub"
}

# ── Locals ─────────────────────────────────────────────────────────────────────
locals {
  images = {
    standard  = { hostname = "standard-001",  mac = "52:54:00:CE:B7:E0", ip = "192.168.100.10", artifact = abspath("${path.module}/../packer/artifacts/standard/standard"),  efivars = abspath("${path.module}/../packer/artifacts/standard/efivars.fd") }
    boot-menu = { hostname = "boot-menu-001", mac = "52:54:00:CE:B7:E1", ip = "192.168.100.11", artifact = abspath("${path.module}/../packer/artifacts/boot-menu/boot-menu"), efivars = abspath("${path.module}/../packer/artifacts/boot-menu/efivars.fd") }
    lvm       = { hostname = "lvm-001",       mac = "52:54:00:CE:B7:E2", ip = "192.168.100.12", artifact = abspath("${path.module}/../packer/artifacts/lvm/lvm"),            efivars = abspath("${path.module}/../packer/artifacts/lvm/efivars.fd") }
  }

  selected = local.images[var.deploy]
}

# ── Network ────────────────────────────────────────────────────────────────────
# vm-network is shared across all three scenarios and is managed once by setup.sh
# via virsh net-define/net-start. It is NOT managed by terraform so that each
# scenario's state file can apply independently without network conflicts.

# Isolated network for the standard VM's second adapter.
# mode = "none" → no DHCP, no routing, no external connectivity.
# The guest OS won't bring the interface up automatically (no NM profile),
# which is the desired "down by default" state for config testing.
resource "libvirt_network" "isolated" {
  count     = var.deploy == "standard" ? 1 : 0
  name      = "vm-isolated"
  mode      = "none"
  autostart = true
}

# ── Base Image Volume ──────────────────────────────────────────────────────────
resource "libvirt_volume" "base" {
  name   = "${var.deploy}-disk.qcow2"
  source = local.selected.artifact
  format = "qcow2"
}

# ── SSH Key Injection ──────────────────────────────────────────────────────────
# Injects lab_key.pub into the offline volume after upload, before first boot.
# The packer_key was cleared from the image at build time, so this is the only
# key that will be present at runtime. Re-running `terraform apply` after
# regenerating lab_key automatically re-injects the new key.
resource "null_resource" "inject_ssh_key" {
  triggers = {
    volume_id        = libvirt_volume.base.id
    ssh_pub_key_hash = filemd5(pathexpand(var.ssh_pub_key_path))
  }

  provisioner "local-exec" {
    command     = "sudo virt-customize -a \"$(virsh vol-path --pool default ${var.deploy}-disk.qcow2)\" --ssh-inject linus:file:${pathexpand(var.ssh_pub_key_path)} --selinux-relabel"
    environment = { LIBGUESTFS_MEMSIZE = "512" }
  }

  depends_on = [libvirt_volume.base]
}

# ── VM ─────────────────────────────────────────────────────────────────────────
resource "libvirt_domain" "vm" {
  name     = local.selected.hostname
  memory   = 3072
  vcpu     = 2
  machine  = "q35"
  firmware = "/usr/share/edk2/ovmf/OVMF_CODE.fd"

  depends_on = [null_resource.inject_ssh_key]

  nvram {
    file     = "/var/lib/libvirt/qemu/nvram/${local.selected.hostname}_VARS.fd"
    template = local.selected.efivars
  }

  cpu {
    mode = "host-passthrough"
  }

  disk {
    volume_id = libvirt_volume.base.id
  }

  network_interface {
    network_name   = "vm-network"
    mac            = local.selected.mac
    wait_for_lease = false
  }

  # Second adapter — standard scenario only, isolated network, down by default.
  dynamic "network_interface" {
    for_each = var.deploy == "standard" ? [1] : []
    content {
      network_id     = libvirt_network.isolated[0].id
      mac            = "52:54:00:CE:B7:E3"
      wait_for_lease = false
    }
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

  graphics {
    type        = "vnc"
    listen_type = "address"
    autoport    = true
  }
}

# ── Outputs ────────────────────────────────────────────────────────────────────
output "vm_hostname" {
  value = local.selected.hostname
}

output "vm_ip" {
  value = local.selected.ip
}

# ── SSH Known-Hosts Cleanup ────────────────────────────────────────────────────
# Each scenario deploys a fresh VM with a new host key at the same IP.
# This automatically removes the stale entry so SSH doesn't complain.
resource "null_resource" "clear_known_hosts" {
  triggers = {
    vm_id = libvirt_domain.vm.id
  }

  provisioner "local-exec" {
    command = "ssh-keygen -R ${local.selected.ip} 2>/dev/null; true"
  }
}
