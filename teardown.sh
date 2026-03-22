#!/bin/bash
# RHCSA Examination Platform — Teardown
# Stops Flask, destroys all 3 VMs, cleans up terraform state files.
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; CYAN='\033[0;36m'; NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
log()  { echo -e "${CYAN}[TEARDOWN]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }

echo -e "${RED}${BOLD}"
echo "╔══════════════════════════════════════╗"
echo "║      RHCSA Lab — Teardown            ║"
echo "╠══════════════════════════════════════╣"
echo "║  This will destroy all 3 VMs and     ║"
echo "║  their snapshots. This is final.     ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"

read -rp "Are you sure? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# Stop Flask if running
if pgrep -f "python.*app\.py" &>/dev/null; then
  log "Stopping Flask server..."
  pkill -f "python.*app\.py" || true
  ok "Flask stopped"
else
  warn "Flask not running"
fi

# Resolve hostname from scenario name
vm_hostname() {
  case "$1" in
    standard)  echo "standard-001"  ;;
    lvm)       echo "lvm-001"       ;;
    boot-menu) echo "boot-menu-001" ;;
  esac
}


# Destroy each VM via its own state file
cd "$TERRAFORM_DIR"
for scenario in standard lvm boot-menu; do
  statefile="${scenario}.tfstate"
  hostname="$(vm_hostname "$scenario")"
  savefile="$PROJECT_ROOT/backend/vm_saves/${hostname}.save"

  # ── Pre-destroy cleanup ──────────────────────────────────────────────────────
  # setup.sh takes an external disk-only snapshot which changes the domain's
  # active disk to the overlay file. The libvirt terraform provider reads the
  # domain XML during destroy and tries to find that overlay as a pool-managed
  # volume — it isn't (it was created via virsh snapshot-create-as, not the pool
  # API), so terraform errors out.
  # Fix: stop the VM, delete the snapshot metadata, and remove the overlay BEFORE
  # terraform destroy so the domain's disk reverts to the base volume (which IS
  # pool-managed and terraform can clean up cleanly).
  overlay_file="/var/lib/libvirt/images/${hostname}-snap.qcow2"

  if virsh dominfo "$hostname" &>/dev/null 2>&1; then
    # Stop the VM.
    virsh destroy "$hostname" 2>/dev/null || true
    # Delete all snapshot metadata so virsh undefine doesn't refuse to proceed.
    for snap in $(virsh snapshot-list "$hostname" --name 2>/dev/null); do
      virsh snapshot-delete "$hostname" "$snap" --metadata 2>/dev/null || true
    done
    # Undefine the domain WITHOUT removing storage.
    # The domain XML references the snapshot overlay as its active disk.
    # Terraform's libvirt provider reads that XML during destroy to resolve disk
    # volumes — the overlay is not pool-managed so the lookup fails with
    # "storage volume not found". Undefining first removes the domain from
    # libvirt entirely; terraform then only cleans up what it tracks in state
    # (the base volume), skipping the missing domain gracefully.
    # UEFI VMs require --nvram to fully undefine; fall back to without it.
    virsh undefine "$hostname" --nvram 2>/dev/null \
      || virsh undefine "$hostname" 2>/dev/null || true
    ok "$hostname: stopped and undefined"
  fi

  # Delete the overlay file — it was created by virsh snapshot-create-as outside
  # of terraform so it will never be cleaned up by terraform destroy.
  rm -f "$overlay_file" 2>/dev/null || sudo rm -f "$overlay_file" 2>/dev/null || true

  if [[ -f "$statefile" ]]; then
    log "Destroying $scenario VM (state: $statefile) ..."
    terraform destroy -state="$statefile" -var="deploy=$scenario" -auto-approve
    ok "$scenario VM destroyed"
  else
    warn "No state file for $scenario — removing via virsh if needed"
    if virsh dominfo "$hostname" &>/dev/null 2>&1; then
      virsh undefine "$hostname" --remove-all-storage 2>/dev/null || true
      ok "$hostname removed via virsh"
    fi
  fi

  # Clean up save file (overlay already removed above)
  if [[ -f "$savefile" ]]; then
    rm -f "$savefile"
    ok "Save file removed: $savefile"
  fi
done

echo -e "\n${GREEN}${BOLD}Teardown complete. All VMs destroyed.${NC}"
