#!/bin/bash
# Configure rd.break to drop into a shell without requiring root password.
#
# Root cause: the dracut-emergency script (run by dracut-emergency.service for
# rd.break) calls `exec sulogin` directly. When root has a password, sulogin
# prompts for it. We patch dracut-emergency in the initramfs to call bash
# instead of sulogin.
#
# Module ordering: 98dracut-systemd installs dracut-emergency; our module 99
# runs after it and patches the script inside ${initdir} at build time.
#
# Multi-kernel: `dnf -y update` may install a newer kernel whose initramfs is
# built before this script runs. We rebuild ALL installed kernels' initramfs.
#
# Result: rd.break drops to bash on VGA (/dev/console = tty0) without any
# password prompt. The emergency shell appears on VGA/VNC, same as sulogin did.

set -e

MODDIR=/usr/lib/dracut/modules.d/99emergency-noauth
sudo mkdir -p "$MODDIR"

sudo tee "$MODDIR/module-setup.sh" > /dev/null << 'EOF'
#!/bin/bash
check()   { return 0; }
depends() { return 0; }
install() {
    inst_binary bash

    # 98dracut-systemd installs dracut-emergency before us (module 99).
    # Patch it to replace "exec sulogin" with bash so rd.break needs no password.
    local em="${initdir}/usr/bin/dracut-emergency"
    if [ -f "${em}" ]; then
        sed -i 's|exec sulogin -e|exec /bin/bash|g' "${em}"
        sed -i 's|exec sulogin$|exec /bin/bash|g'   "${em}"
        sed -i 's|exec sulogin |exec /bin/bash |g'  "${em}"
        echo "[99emergency-noauth] Patched dracut-emergency: sulogin → bash"
    else
        echo "[99emergency-noauth] WARNING: dracut-emergency not found at ${em}"
    fi
}
EOF

sudo chmod +x "$MODDIR/module-setup.sh"

echo "[configure-emergency-shell] dracut module written to $MODDIR"

# Rebuild initramfs for ALL installed kernels.
for kver in $(rpm -q kernel --qf '%{VERSION}-%{RELEASE}.%{ARCH}\n'); do
    IMG=/boot/initramfs-${kver}.img
    echo "[configure-emergency-shell] rebuilding $IMG"
    sudo dracut --force "$IMG" "$kver"
done

echo "[configure-emergency-shell] done — rd.break drops to bash without password prompt"
