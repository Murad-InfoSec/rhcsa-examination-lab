#!/bin/bash
# RHCSA Examination Platform — Full Setup
# Usage: ./setup.sh
set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
PACKER_DIR="$PROJECT_ROOT/packer"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
VENV="$BACKEND_DIR/rhcsa-lab"
SAVE_DIR="$BACKEND_DIR/vm_saves"

export PATH="$HOME/.local/bin:$VENV/bin:$PATH"

# ── Progress tracking ──────────────────────────────────────────────────────────
# Total steps (packer steps counted even if skipped, so % stays accurate):
#   prerequisites(1) permissions(1) ssh-keys(1)
#   packer x3(3) venv(1) frontend(1) tf-init(1) vm-network(1)
#   per-VM x3: terraform(1) boot-wait(1) snapshot(1) checkpoint(1) = 12
#   platform-ready(1)  →  23 total
TOTAL_STEPS=23
STEP=0

progress() {
  STEP=$(( STEP + 1 ))
  local pct=$(( STEP * 100 / TOTAL_STEPS ))
  local bar_done=$(( pct / 5 ))          # 20-char bar
  local bar_left=$(( 20 - bar_done ))
  local bar
  bar="$(printf '%0.s█' $(seq 1 $bar_done) 2>/dev/null || true)"
  bar+="$(printf '%0.s░' $(seq 1 $bar_left) 2>/dev/null || true)"
  echo -e "\n${BOLD}${BLUE}[${STEP}/${TOTAL_STEPS}] ${bar} ${pct}%${NC}  ${BOLD}$*${NC}"
}

ok()   { echo -e "  ${GREEN}✔${NC}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
fail() { echo -e "\n${RED}${BOLD}✘ FAILED:${NC} $*" >&2; exit 1; }

# ── PHASE 1 — Prerequisites ────────────────────────────────────────────────────
progress "Installing prerequisites"

# ── 1a: System packages via dnf ───────────────────────────────────────────────
DNF_PKGS=()
command -v virsh          &>/dev/null || DNF_PKGS+=(libvirt virt-install
                                                    libvirt-daemon-config-network
                                                    libvirt-daemon-kvm)
command -v virt-customize &>/dev/null || DNF_PKGS+=(guestfs-tools)
command -v python3        &>/dev/null || DNF_PKGS+=(python3 python3-pip)
{ command -v node &>/dev/null && command -v npm &>/dev/null; } \
                                      || DNF_PKGS+=(nodejs npm)
command -v qemu-img       &>/dev/null || DNF_PKGS+=(qemu-img)
{ command -v qemu-system-x86_64 &>/dev/null \
  || [[ -x /usr/libexec/qemu-kvm ]]; }  || DNF_PKGS+=(qemu-kvm)
command -v ansible-vault  &>/dev/null || DNF_PKGS+=(ansible-core)
command -v ssh-keygen     &>/dev/null || DNF_PKGS+=(openssh-clients)
command -v openssl        &>/dev/null || DNF_PKGS+=(openssl)
# UEFI firmware required by Packer + Terraform (OVMF_CODE.fd / OVMF_VARS.fd)
[[ -f /usr/share/edk2/ovmf/OVMF_CODE.fd ]] || DNF_PKGS+=(edk2-ovmf)

if [[ ${#DNF_PKGS[@]} -gt 0 ]]; then
  echo -e "  Installing system packages: ${DNF_PKGS[*]}"
  sudo dnf install -y "${DNF_PKGS[@]}"
  ok "System packages installed"
else
  ok "System packages already present"
fi

for cmd in virsh virt-customize python3 npm qemu-img ansible-vault ssh-keygen openssl; do
  # qemu-system-x86_64 is verified separately after the symlink step
  command -v "$cmd" &>/dev/null \
    && ok "$cmd → $(command -v "$cmd")" \
    || fail "$cmd not available after install — check dnf output above"
done
[[ -f /usr/share/edk2/ovmf/OVMF_CODE.fd ]] \
  && ok "edk2-ovmf → /usr/share/edk2/ovmf/OVMF_CODE.fd" \
  || fail "OVMF_CODE.fd not found after edk2-ovmf install"

# On RHEL/AlmaLinux qemu-kvm lands in /usr/libexec, not PATH.
# Packer's qemu plugin requires qemu-system-x86_64 by name — symlink it.
if ! command -v qemu-system-x86_64 &>/dev/null; then
  if [[ -x /usr/libexec/qemu-kvm ]]; then
    sudo ln -sf /usr/libexec/qemu-kvm /usr/local/bin/qemu-system-x86_64
    ok "qemu-system-x86_64 → /usr/libexec/qemu-kvm (symlink)"
  else
    fail "qemu-kvm not found in /usr/libexec — qemu-kvm package missing"
  fi
else
  ok "qemu-system-x86_64 → $(command -v qemu-system-x86_64)"
fi

# ── 1b: Enable + start libvirtd ───────────────────────────────────────────────
if ! systemctl is-active --quiet libvirtd 2>/dev/null; then
  sudo systemctl enable --now libvirtd
  ok "libvirtd enabled and started"
else
  ok "libvirtd running"
fi

# ── 1c: Terraform + Packer (HashiCorp DNF repo) ───────────────────────────────
if ! command -v terraform &>/dev/null || ! command -v packer &>/dev/null; then
  if ! dnf repolist 2>/dev/null | grep -qi hashicorp; then
    # dnf5-plugins on AlmaLinux/RHEL 10; dnf-plugins-core on older releases
    if rpm -q dnf5-plugins &>/dev/null || dnf list installed dnf5-plugins &>/dev/null 2>&1; then
      sudo dnf install -y dnf5-plugins
    else
      sudo dnf install -y dnf-plugins-core
    fi
    sudo dnf config-manager addrepo \
      --from-repofile=https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo \
      2>/dev/null \
      || sudo dnf config-manager --add-repo \
           https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
    ok "HashiCorp repo added"
  else
    ok "HashiCorp repo already present"
  fi
  command -v terraform &>/dev/null || sudo dnf install -y terraform
  command -v packer    &>/dev/null || sudo dnf install -y packer
fi
ok "terraform → $(command -v terraform)"
ok "packer    → $(command -v packer)"

# ── 1d: websockify via pip3 ───────────────────────────────────────────────────
# ansible-core is installed via dnf above; websockify is pip-only.
if ! command -v websockify &>/dev/null; then
  pip3 install --user --quiet websockify \
    && { hash -r 2>/dev/null || true; ok "websockify installed (pip3 --user)"; } \
    || warn "websockify pip3 install failed — will retry inside venv (PHASE 5)"
else
  ok "websockify → $(command -v websockify)"
fi

# ── PHASE 2 — Permissions ──────────────────────────────────────────────────────
progress "Fixing permissions"

for grp in kvm libvirt qemu; do
  if getent group "$grp" &>/dev/null; then
    if id -nG "$USER" | grep -qw "$grp"; then ok "Already in group: $grp"
    else sudo usermod -aG "$grp" "$USER"; ok "Added $USER → $grp (re-login for full effect)"; fi
  fi
done

if [[ "$(stat -c '%U' "$PROJECT_ROOT")" != "$USER" ]]; then
  sudo chown -R "$USER:$USER" "$PROJECT_ROOT"
  ok "Ownership fixed: $PROJECT_ROOT → $USER"
else
  ok "Ownership correct"
fi

# Allow virt-customize to run without a password (needed by terraform local-exec)
SUDOERS_FILE="/etc/sudoers.d/virt-customize-nopasswd"
if [[ ! -f "$SUDOERS_FILE" ]]; then
  echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/virt-customize" | sudo tee "$SUDOERS_FILE" > /dev/null
  sudo chmod 440 "$SUDOERS_FILE"
  ok "sudoers rule added for virt-customize"
else
  ok "sudoers rule already present"
fi

# ── PHASE 3 — SSH keys ─────────────────────────────────────────────────────────
progress "SSH keys"

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

if [[ -f "$HOME/.ssh/packer_key" && -f "$HOME/.ssh/packer_key.pub" ]]; then
  ok "packer_key already exists"
else
  ssh-keygen -t ed25519 -C "packer-build" -f "$HOME/.ssh/packer_key" -N ""
  ok "packer_key generated"
fi

if [[ -f "$HOME/.ssh/lab_key" && -f "$HOME/.ssh/lab_key.pub" ]]; then
  ok "lab_key already exists"
else
  ssh-keygen -t ed25519 -C "rhcsa-lab" -f "$HOME/.ssh/lab_key" -N ""
  ok "lab_key generated"
fi

chmod 600 "$HOME/.ssh/packer_key" "$HOME/.ssh/lab_key"
chmod 644 "$HOME/.ssh/packer_key.pub" "$HOME/.ssh/lab_key.pub"

# Inject the packer public key into all kickstart files, replacing the placeholder.
# This runs every time so a regenerated packer_key is always current before builds.
packer_pub="$(cat "$HOME/.ssh/packer_key.pub")"
# Replace any ssh-ed25519 line in the kickstart authorized_keys block.
# The old pattern matched only lines ending with 'packer-build' which silently
# failed when the comment was anything else (e.g. 'user@host').
for ks in "$PACKER_DIR/http/ks-standard.cfg" \
           "$PACKER_DIR/http/ks-boot-menu.cfg" \
           "$PACKER_DIR/http/ks-lvm.cfg"; do
  sed -i "s|^ssh-ed25519 .*|${packer_pub}|" "$ks"
  grep -q "^${packer_pub}$" "$ks" \
    || fail "Key injection failed for $(basename "$ks")"
done
ok "Packer public key injected into kickstart files"

# ── Ansible Vault password + encrypted secrets ─────────────────────────────────
mkdir -p "$HOME/.ansible"
if [[ ! -f "$HOME/.ansible/vault_pass" ]]; then
  openssl rand -hex 256 > "$HOME/.ansible/vault_pass"
  chmod 600 "$HOME/.ansible/vault_pass"
  ok "Vault password generated: ~/.ansible/vault_pass"
else
  ok "Vault password exists: ~/.ansible/vault_pass"
fi

# Write lab_key content into vault.yml (plaintext) then encrypt.
# Always rewritten so a regenerated lab_key is automatically picked up.
{
  echo "vault_ssh_private_key: |"
  sed 's/^/  /' "$HOME/.ssh/lab_key"
} > "$BACKEND_DIR/ansible/vault.yml"
"$VENV/bin/ansible-vault" encrypt "$BACKEND_DIR/ansible/vault.yml" \
  --vault-password-file "$HOME/.ansible/vault_pass" 2>/dev/null \
  || ansible-vault encrypt "$BACKEND_DIR/ansible/vault.yml" \
       --vault-password-file "$HOME/.ansible/vault_pass"
ok "ansible/vault.yml encrypted with lab_key"

# ── PHASE 4 — Packer builds (counted even when skipped) ───────────────────────
cd "$PACKER_DIR"

# Init plugins once using a single file to avoid duplicate required_plugin
# errors that occur when all three HCL files declare the same qemu plugin.
packer init standard.pkr.hcl
ok "Packer plugins initialised"

for scenario in boot-menu lvm standard; do
  progress "Packer — $scenario"
  artifact="$PACKER_DIR/artifacts/$scenario"
  if [[ -d "$artifact" ]] && compgen -G "$artifact/*" &>/dev/null; then
    ok "Artifact exists, skipping build"
  else
    packer build "${scenario}.pkr.hcl"
    ok "Packer build done: $scenario"
  fi
done
cd "$PROJECT_ROOT"

# ── PHASE 5 — Python venv ──────────────────────────────────────────────────────
progress "Python virtualenv + dependencies"

if [[ ! -f "$VENV/bin/activate" ]]; then
  python3 -m venv "$VENV"
  ok "Virtualenv created: $VENV"
else
  ok "Virtualenv exists"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$BACKEND_DIR/requirements.txt"
ok "Python dependencies installed"

# ── PHASE 6 — Frontend build ───────────────────────────────────────────────────
progress "Frontend build"

cd "$FRONTEND_DIR"
if [[ ! -d "node_modules" ]]; then npm install --silent; ok "npm packages installed"
else ok "node_modules present"; fi

if [[ ! -f "$BACKEND_DIR/frontend_dist/index.html" ]]; then
  npm run build
  ok "Frontend built → $BACKEND_DIR/frontend_dist/"
else
  ok "Frontend already built"
fi
cd "$PROJECT_ROOT"

# ── PHASE 7 — VM infrastructure ───────────────────────────────────────────────
progress "Terraform init + vm-network"

declare -A VM_IP=([standard]="192.168.100.10" [lvm]="192.168.100.12" [boot-menu]="192.168.100.11")
declare -A VM_HOSTNAME=([standard]="standard-001" [lvm]="lvm-001" [boot-menu]="boot-menu-001")

cd "$TERRAFORM_DIR"
if [[ ! -d ".terraform" ]]; then terraform init; fi
ok "Terraform ready"

if virsh net-info vm-network &>/dev/null; then
  virsh net-destroy vm-network 2>/dev/null || true
  virsh net-undefine vm-network 2>/dev/null || true
  ok "vm-network removed (will recreate)"
fi
virsh net-define /dev/stdin <<'NETXML'
<network>
  <name>vm-network</name>
  <forward mode="nat"/>
  <dns enable="yes"/>
  <ip address="192.168.100.1" prefix="24"/>
</network>
NETXML
virsh net-start vm-network
virsh net-autostart vm-network
ok "vm-network created"

# ── Helpers ────────────────────────────────────────────────────────────────────
wait_for_ssh() {
  local ip="$1" n=0 max=360
  echo -ne "  Waiting for SSH on $ip "
  while [[ $n -lt $max ]]; do
    if ssh -i "$HOME/.ssh/lab_key" \
           -o StrictHostKeyChecking=no \
           -o ConnectTimeout=3 \
           linus@"$ip" exit 0 &>/dev/null; then
      echo -e " ${GREEN}ready${NC}"
      return 0
    fi
    echo -n "."; sleep 2; n=$(( n + 1 ))
  done
  echo ""
  fail "Timed out waiting for SSH on $ip"
}

take_snapshot() {
  local hostname="$1"
  local overlay="/var/lib/libvirt/images/${hostname}-snap.qcow2"
  if virsh snapshot-list "$hostname" --name 2>/dev/null | grep -qx "initial"; then
    ok "Disk snapshot 'initial' already exists"
  else
    virsh snapshot-create-as "$hostname" initial \
      --disk-only \
      --diskspec "vda,snapshot=external,file=${overlay}" \
      --atomic
    ok "Disk snapshot taken (overlay: $overlay)"
  fi
}

save_mem_checkpoint() {
  local hostname="$1"
  local savefile="$SAVE_DIR/${hostname}.save"
  mkdir -p "$SAVE_DIR"
  if ! virsh save "$hostname" "$savefile" 2>/dev/null; then
    warn "virsh save failed — app will cold-boot this VM (no checkpoint)"
    return 0
  fi
  ok "Memory checkpoint saved: $savefile"
  # All VMs are left stopped after checkpointing.
  # app.py's _startup_vm_worker starts standard on launch via virsh restore.
}

# ── PHASE 7 — VM deployment ────────────────────────────────────────────────────
# Process in order: boot-menu → lvm → standard.
# Each VM is fully completed (terraform + boot + snapshot + checkpoint) before
# the next one starts. boot-menu and lvm are left stopped after checkpointing
# so only one VM runs at a time. standard is last and stays running.

for scenario in boot-menu lvm standard; do
  hostname="${VM_HOSTNAME[$scenario]}"
  ip="${VM_IP[$scenario]}"
  statefile="${scenario}.tfstate"
  savefile="$SAVE_DIR/${hostname}.save"

  # ── Step: Terraform apply ──────────────────────────────────────────────────
  progress "[$scenario] Terraform apply"

  # Refresh sudo timestamp so virt-customize in terraform local-exec can run
  # without a password prompt (sudo may have timed out during packer builds).
  sudo -v

  virsh pool-refresh default 2>/dev/null || true

  # If statefile + save file + snap overlay all exist, this VM is fully set up — skip all steps.
  if [[ -f "$statefile" && -f "$savefile" ]] && \
     virsh vol-info "${hostname}-snap.qcow2" --pool default &>/dev/null 2>&1; then
    ok "$hostname already complete — skipping"
    progress "[$scenario] Waiting for boot"; ok "Skipped"
    progress "[$scenario] Disk snapshot";    ok "Skipped"
    progress "[$scenario] Memory checkpoint"; ok "Skipped"
    continue
  fi

  # Otherwise clean up completely before re-creating.
  if virsh vol-info "${hostname}-snap.qcow2" --pool default &>/dev/null 2>&1; then
    virsh vol-delete "${hostname}-snap.qcow2" --pool default 2>/dev/null \
      || rm -f "/var/lib/libvirt/images/${hostname}-snap.qcow2" 2>/dev/null \
      || sudo rm -f "/var/lib/libvirt/images/${hostname}-snap.qcow2" || true
    ok "Removed stale overlay"
  fi
  if [[ -f "$savefile" ]]; then rm -f "$savefile"; ok "Removed stale save file"; fi
  if virsh dominfo "$hostname" &>/dev/null 2>&1; then
    virsh destroy "$hostname" 2>/dev/null || true
    # Remove snapshot metadata first so undefine doesn't choke on missing overlay files
    for snap in $(virsh snapshot-list "$hostname" --name 2>/dev/null); do
      virsh snapshot-delete "$hostname" "$snap" --metadata 2>/dev/null || true
    done
    virsh undefine "$hostname" --remove-all-storage --nvram 2>/dev/null \
      || virsh undefine "$hostname" --nvram 2>/dev/null || true
    # Manually remove base volume in case undefine left it behind
    virsh vol-delete "${scenario}-disk.qcow2" --pool default 2>/dev/null || true
    ok "Removed stale domain"
  fi
  # Standard uses an isolated network managed by Terraform; remove it so terraform can recreate it
  if [[ "$scenario" == "standard" ]]; then
    virsh net-destroy vm-isolated 2>/dev/null || true
    virsh net-undefine vm-isolated 2>/dev/null || true
  fi
  [[ -f "$statefile" ]] && rm -f "$statefile"

  terraform apply -state="$statefile" -var="deploy=$scenario" -var="ssh_pub_key_path=$HOME/.ssh/lab_key.pub" -auto-approve
  ok "$hostname created"

  # ── Step: Wait for boot ───────────────────────────────────────────────────
  progress "[$scenario] Waiting for boot"

  if [[ "$scenario" == "boot-menu" ]]; then
    echo -ne "  Waiting for $hostname to run "
    for _ in $(seq 1 30); do
      virsh domstate "$hostname" 2>/dev/null | grep -q "running" && break
      echo -n "."; sleep 2
    done
    echo -e " ${GREEN}running${NC}"
  else
    wait_for_ssh "$ip"
  fi

  # ── Step: Disk snapshot ───────────────────────────────────────────────────
  progress "[$scenario] Disk snapshot"
  take_snapshot "$hostname"

  # ── Step: Memory checkpoint ───────────────────────────────────────────────
  progress "[$scenario] Memory checkpoint"
  save_mem_checkpoint "$hostname"
done

cd "$PROJECT_ROOT"

# ── PHASE 8 — Done ─────────────────────────────────────────────────────────────
progress "Setup complete — all 3 VMs ready"

echo -e "\n${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║       All VMs created and checkpointed       ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  boot-menu-001  →  stopped (checkpoint ready)  ║"
echo "║  lvm-001        →  stopped (checkpoint ready)  ║"
echo "║  standard-001   →  stopped (app.py will start) ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ── PHASE 9 — Start platform ───────────────────────────────────────────────────
echo -e "${YELLOW}"
read -rp "Which exam? [exam-1/exam-2] (default: exam-1): " EXAM_CHOICE || true
EXAM="${EXAM_CHOICE:-exam-1}"
echo -e "${NC}"

echo -e "${CYAN}"
echo "╔══════════════════════════════════════╗"
echo "║   RHCSA Examination Platform Ready   ║"
echo "╠══════════════════════════════════════╣"
printf "║  Exam : %-29s║\n" "$EXAM"
printf "║  URL  : %-29s║\n" "http://localhost:5000"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"

PROJECT_ROOT="$PROJECT_ROOT" \
ACTIVE_SCENARIO=standard \
ACTIVE_EXAM="$EXAM" \
SSH_KEY_PATH="$HOME/.ssh/lab_key" \
"$VENV/bin/python" "$BACKEND_DIR/app.py"
