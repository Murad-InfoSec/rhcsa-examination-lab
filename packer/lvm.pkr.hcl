packer {
  required_plugins {
    qemu = {
      source  = "github.com/hashicorp/qemu"
      version = ">= 1.0.0"
    }
  }
}

source "qemu" "lvm" {

  iso_url      = "${path.root}/AlmaLinux-10.1-x86_64-minimal.iso"
  iso_checksum = "sha256:049efd183a5a841dd432b3427eb6faa7deb3bf6c6bf2c63cbffa024b9c651725"

  output_directory = "${path.root}/artifacts/lvm"
  vm_name          = "lvm"
  format           = "qcow2"
  disk_size        = 20480

  memory = 3072
  cpus   = 2

  net_device  = "virtio-net"
  accelerator  = "kvm"
  cpu_model    = "host"
  headless     = true
  qemu_binary  = "/usr/bin/qemu-system-x86_64"

  machine_type = "q35"

  efi_firmware_code = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
  efi_firmware_vars = "/usr/share/edk2/ovmf/OVMF_VARS.fd"

  http_directory = "${path.root}/http"
  boot_wait      = "30s"
  boot_command = [
    "<up><wait>",
    "e<wait2>",
    "<down><down><end>",
    " inst.ks=http://{{ .HTTPIP }}:{{ .HTTPPort }}/ks-lvm.cfg net.ifnames=0 biosdevname=0 console=ttyS0,115200n8",
    "<leftCtrlOn>x<leftCtrlOff>"
  ]

  ssh_username         = "linus"
  ssh_private_key_file = "~/.ssh/packer_key"
  ssh_timeout          = "60m"

  # Disk is already qcow2 from the start; skip_compaction avoids the
  # stepConvertDisk relative-path bug ("No such file or directory").
  skip_compaction = true

  qemuargs = [
    ["-serial", "file:/tmp/vm-serial.log"],
  ]

  shutdown_command = "sudo shutdown -h now"
}


build {
  sources = ["source.qemu.lvm"]

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

      # Write static NM keyfile
      "sudo mkdir -p /etc/NetworkManager/system-connections",
      "printf '[connection]\\nid=static\\ntype=ethernet\\nautoconnect=true\\nautoconnect-priority=100\\n\\n[ethernet]\\nmac-address=52:54:00:CE:B7:E2\\n\\n[ipv4]\\nmethod=manual\\naddress1=192.168.100.12/24\\n\\n[ipv6]\\nmethod=ignore\\n' | sudo tee /etc/NetworkManager/system-connections/static.nmconnection > /dev/null",
      "sudo chmod 600 /etc/NetworkManager/system-connections/static.nmconnection",
      "sudo restorecon -v /etc/NetworkManager/system-connections/static.nmconnection 2>/dev/null || true",

      #Give user enough priviliages to perfom RHCSA tasks
      "sudo usermod -aG wheel linus",
      "echo 'linus ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/linus",
      "sudo chmod 440 /etc/sudoers.d/linus",

      # Install LVM tooling (gdisk not available in AlmaLinux 10.1 repos; parted handles GPT)
      "sudo dnf install -y lvm2 parted",

      # Install podman and rsync
      "sudo dnf install -y podman rsync",

      # Create /data logical volume from free space in the almalinux VG
      "sudo lvcreate -L 5G -n data almalinux",
      "sudo mkfs.ext4 -L data /dev/almalinux/data",
      "sudo mkdir -p /data",
      "echo 'LABEL=data  /data  ext4  defaults,noatime  0 2' | sudo tee -a /etc/fstab",
      "sudo mount /data",

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
