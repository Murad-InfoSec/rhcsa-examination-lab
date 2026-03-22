packer {
  required_plugins {
    qemu = {
      source  = "github.com/hashicorp/qemu"
      version = ">= 1.0.0"
    }
  }
}

source "qemu" "standard" {

  iso_url      = "${path.root}/AlmaLinux-10.1-x86_64-minimal.iso"
  iso_checksum = "sha256:049efd183a5a841dd432b3427eb6faa7deb3bf6c6bf2c63cbffa024b9c651725"

  output_directory = "${path.root}/artifacts/standard"
  vm_name          = "standard"
  format           = "qcow2"
  disk_size        = 10240

  memory = 3072
  cpus   = 2

  net_device  = "virtio-net"
  accelerator = "kvm"
  cpu_model   = "host"
  headless    = true

  machine_type = "q35"

  efi_firmware_code = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
  efi_firmware_vars = "/usr/share/edk2/ovmf/OVMF_VARS.fd"

  http_directory = "${path.root}/http"
  boot_wait      = "30s"
  boot_command = [
    "<up><wait>",
    "e<wait2>",
    "<down><down><end>",
    " inst.ks=http://{{ .HTTPIP }}:{{ .HTTPPort }}/ks-standard.cfg net.ifnames=0 biosdevname=0 console=ttyS0,115200n8",
    "<leftCtrlOn>x<leftCtrlOff>"
  ]

  ssh_username         = "linus"
  ssh_private_key_file = "~/.ssh/packer_key"
  ssh_timeout          = "60m"

  qemuargs = [
    ["-serial", "file:/tmp/vm-serial.log"],
  ]

  shutdown_command = "sudo shutdown -h now"
}


build {
  sources = ["source.qemu.standard"]

  provisioner "shell" {
    inline = [
      # Update base system
      "sudo dnf -y update",

      # rsync required for dep injection at terraform apply time
      "sudo dnf install -y rsync",

      # Enable serial console
      "sudo systemctl enable serial-getty@ttyS0.service",

      # Configure GRUB for serial console output (idempotent with sed)
      "sudo sed -i '/^GRUB_TIMEOUT=/d' /etc/default/grub",
      "sudo sed -i '/^GRUB_CMDLINE_LINUX=/d' /etc/default/grub",
      "echo 'GRUB_TIMEOUT=1' | sudo tee -a /etc/default/grub",
      "echo 'GRUB_CMDLINE_LINUX=\"console=tty0 console=ttyS0,115200n8\"' | sudo tee -a /etc/default/grub",

      # Update existing BLS kernel entries
      "sudo grubby --update-kernel=ALL --remove-args='net.ifnames biosdevname'",
      "sudo grubby --update-kernel=ALL --args='console=tty0 console=ttyS0,115200n8'",

      # Regenerate GRUB config
      "sudo grub2-mkconfig -o /boot/grub2/grub.cfg",
      "[ -d /boot/efi/EFI/almalinux ] && sudo grub2-mkconfig -o /boot/efi/EFI/almalinux/grub.cfg || true",

      # Write static NM keyfile — MAC-based so it activates on enp1s0 (or any name)
      # when terraform deploys with mac 52:54:00:ce:b7:e0. During packer build the
      # MAC differs so this connection stays inactive; DHCP handles packer SSH.
      # No gateway or DNS — VMs have no internet access.
      "sudo mkdir -p /etc/NetworkManager/system-connections",
      "printf '[connection]\\nid=static\\ntype=ethernet\\nautoconnect=true\\nautoconnect-priority=100\\n\\n[ethernet]\\nmac-address=52:54:00:CE:B7:E0\\n\\n[ipv4]\\nmethod=manual\\naddress1=192.168.100.10/24\\n\\n[ipv6]\\nmethod=ignore\\n' | sudo tee /etc/NetworkManager/system-connections/static.nmconnection > /dev/null",
      "sudo chmod 600 /etc/NetworkManager/system-connections/static.nmconnection",
      "sudo restorecon -v /etc/NetworkManager/system-connections/static.nmconnection 2>/dev/null || true",

      # enp2s0 — second adapter (MAC 52:54:00:CE:B7:E3, isolated network).
      # Explicit profile with autoconnect=false keeps the interface down by default.
      "printf '[connection]\\nid=enp2s0-disabled\\ntype=ethernet\\nautoconnect=false\\n\\n[ethernet]\\nmac-address=52:54:00:CE:B7:E3\\n\\n[ipv4]\\nmethod=disabled\\n\\n[ipv6]\\nmethod=disabled\\n' | sudo tee /etc/NetworkManager/system-connections/enp2s0-disabled.nmconnection > /dev/null",
      "sudo chmod 600 /etc/NetworkManager/system-connections/enp2s0-disabled.nmconnection",
      "sudo restorecon -v /etc/NetworkManager/system-connections/enp2s0-disabled.nmconnection 2>/dev/null || true",

      #Give user enough priviliages to perfom RHCSA tasks
      "sudo usermod -aG wheel linus",
      "echo 'linus ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/linus",
      "sudo chmod 440 /etc/sudoers.d/linus",

      # Install tuned for the tuned profile task
      "sudo dnf install -y tuned",

      # Install podman and rsync
      "sudo dnf install -y podman rsync",

      # Clear packer build key — Terraform injects lab_key at apply time
      "truncate -s 0 /home/linus/.ssh/authorized_keys",

      # Clean image for cloning
      "sudo truncate -s 0 /etc/machine-id",
      "sudo rm -rf /var/lib/cloud/*",
      "sudo dnf clean all",
      "sudo rm -rf /tmp/*"
    ]
  }
}
