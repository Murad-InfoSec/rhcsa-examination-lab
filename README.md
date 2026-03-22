<div align="center">

# RHCSA Examination Lab

<img src="https://img.shields.io/badge/AlmaLinux-10.1-00B9E4?style=for-the-badge&logo=almalinux&logoColor=white" alt="AlmaLinux">
<img src="https://img.shields.io/badge/KVM%2FLibvirt-VM-orange?style=for-the-badge&logo=linux&logoColor=white" alt="KVM">
<img src="https://img.shields.io/badge/Packer-built-02A8EF?style=for-the-badge&logo=packer&logoColor=white" alt="Packer">
<img src="https://img.shields.io/badge/Terraform-provisioned-7B42BC?style=for-the-badge&logo=terraform&logoColor=white" alt="Terraform">
<img src="https://img.shields.io/badge/Flask-backend-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask">
<img src="https://img.shields.io/badge/React-frontend-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React">

<br/><br/>

**A self-hosted, browser-based exam platform for practising and taking RHCSA-style examinations inside real AlmaLinux VMs.**

</div>

---

## Table of Contents

<ul>
  <li><a href="#overview">Overview</a></li>
  <li><a href="#architecture">Architecture</a></li>
  <li><a href="#exam-scenarios">Exam Scenarios</a></li>
  <li><a href="#prerequisites">Prerequisites</a></li>
  <li><a href="#quick-start">Quick Start</a></li>
  <li><a href="#project-structure">Project Structure</a></li>
  <li><a href="#teardown">Teardown</a></li>
  <li><a href="#running-individual-scenarios">Running Individual Scenarios</a></li>
  <li><a href="#how-it-works">How It Works</a></li>
</ul>

---

## Overview

The RHCSA Examination Lab creates a realistic exam environment by spinning up **AlmaLinux 10.1 KVM virtual machines** from scratch, presenting the candidate with a timed, task-based exam through a web UI, and automatically grading answers using Ansible playbooks.

Three distinct VM scenarios are supported, each targeting a different area of the RHCSA syllabus. VMs are built once via Packer, checkpointed, and restored to a clean state between exam attempts — no re-install required.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser (localhost:5000)             │
│   ┌────────────────────┐      ┌───────────────────────┐     │
│   │  React + TypeScript│      │   noVNC / Websockify  │     │
│   │  (exam UI + timer) │      │   (VM console access) │     │
│   └────────┬───────────┘      └──────────┬────────────┘     │
└────────────┼────────────────────────────-┼──────────────────┘
             │ REST / SSE                  │ WebSocket
┌────────────▼─────────────────────────────▼──────────────────┐
│                    Flask Backend (app.py)                    │
│   exam_loader  ·  vm_config  ·  ansible_checker             │
└────────────┬────────────────────────────────────────────────┘
             │ virsh / SSH
┌────────────▼────────────────────────────────────────────────┐
│               KVM / libvirt (vm-network 192.168.100.0/24)   │
│   ┌──────────────┐  ┌──────────────┐  ┌───────────────┐    │
│   │ standard-001 │  │  lvm-001     │  │ boot-menu-001 │    │
│   │ .100.10      │  │  .100.12     │  │  .100.11      │    │
│   └──────────────┘  └──────────────┘  └───────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

<table>
<thead>
  <tr>
    <th>Component</th>
    <th>Technology</th>
    <th>Purpose</th>
  </tr>
</thead>
<tbody>
  <tr>
    <td>VM images</td>
    <td>Packer + Kickstart</td>
    <td>Build reproducible AlmaLinux 10.1 qcow2 images</td>
  </tr>
  <tr>
    <td>VM provisioning</td>
    <td>Terraform (libvirt provider)</td>
    <td>Deploy, network, and manage VM lifecycle</td>
  </tr>
  <tr>
    <td>Exam grading</td>
    <td>Ansible playbooks</td>
    <td>SSH into VMs and verify task completion</td>
  </tr>
  <tr>
    <td>Backend API</td>
    <td>Flask (Python)</td>
    <td>Serve exam content, trigger grading, manage VMs</td>
  </tr>
  <tr>
    <td>Frontend</td>
    <td>React + TypeScript + Vite</td>
    <td>Exam timer, task list, VNC console, score display</td>
  </tr>
  <tr>
    <td>Console access</td>
    <td>Websockify + noVNC</td>
    <td>Browser-based VM console (no SSH client needed)</td>
  </tr>
</tbody>
</table>

---

## Exam Scenarios

<table>
<thead>
  <tr>
    <th>Scenario</th>
    <th>VM Hostname</th>
    <th>IP</th>
    <th>Focus Areas</th>
  </tr>
</thead>
<tbody>
  <tr>
    <td><code>standard</code></td>
    <td>standard-001</td>
    <td>192.168.100.10</td>
    <td>Users, groups, permissions, SELinux, services, storage, networking</td>
  </tr>
  <tr>
    <td><code>lvm</code></td>
    <td>lvm-001</td>
    <td>192.168.100.12</td>
    <td>LVM — PV / VG / LV creation, resizing, filesystem management</td>
  </tr>
  <tr>
    <td><code>boot-menu</code></td>
    <td>boot-menu-001</td>
    <td>192.168.100.11</td>
    <td>GRUB2, boot targets, kernel parameters, emergency/rescue mode</td>
  </tr>
</tbody>
</table>

Multiple exam papers per scenario are supported (`exam-1.json`, `exam-2.json`, …).

---

## Prerequisites

The following tools must be installed on the host before running `setup.sh`:

<table>
<thead>
  <tr><th>Tool</th><th>Install command (Fedora / RHEL / AlmaLinux)</th></tr>
</thead>
<tbody>
  <tr><td>virsh / libvirt</td><td><code>sudo dnf install libvirt virt-install</code></td></tr>
  <tr><td>virt-customize</td><td><code>sudo dnf install libguestfs-tools</code></td></tr>
  <tr><td>Packer</td><td><a href="https://developer.hashicorp.com/packer/downloads">hashicorp.com/packer/downloads</a></td></tr>
  <tr><td>Terraform</td><td><a href="https://developer.hashicorp.com/terraform/downloads">hashicorp.com/terraform/downloads</a></td></tr>
  <tr><td>Python 3</td><td><code>sudo dnf install python3</code></td></tr>
  <tr><td>Node.js / npm</td><td><code>sudo dnf install nodejs npm</code></td></tr>
  <tr><td>ansible</td><td>auto-installed by <code>setup.sh</code></td></tr>
  <tr><td>websockify</td><td>auto-installed by <code>setup.sh</code></td></tr>
</tbody>
</table>

The host must be able to run KVM hardware-accelerated VMs (`/dev/kvm` accessible).

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/<you>/rhcsa-examination-lab.git
cd rhcsa-examination-lab

# 2. Place the AlmaLinux 10.1 minimal ISO into the packer directory
#    (already present if you cloned with LFS or downloaded separately)
ls packer/AlmaLinux-10.1-x86_64-minimal.iso

# 3. Run the one-shot setup — builds VMs, checkpoints them, starts the platform
./setup.sh

# 4. Open your browser
xdg-open http://localhost:5000
```

`setup.sh` is fully idempotent. Re-running it skips steps whose artifacts already exist (Packer images, VM snapshots, etc.).

---

## Project Structure

```
rhcsa-examination-lab/
├── packer/                     # Packer HCL templates + Kickstart configs
│   ├── standard.pkr.hcl
│   ├── lvm.pkr.hcl
│   ├── boot-menu.pkr.hcl
│   ├── http/                   # Kickstart files served during install
│   ├── scripts/                # Post-install provisioning scripts
│   ├── artifacts/              # Built qcow2 images (generated)
│   └── AlmaLinux-10.1-x86_64-minimal.iso
│
├── terraform/                  # Libvirt provider — VM definitions
│   └── main.tf
│
├── backend/                    # Flask API + grading engine
│   ├── app.py                  # Main Flask application
│   ├── exam_loader.py          # Parses exam JSON files
│   ├── vm_config.py            # VM metadata (IPs, hostnames, scenarios)
│   ├── ansible_checker.py      # Runs Ansible playbooks to grade tasks
│   ├── exams/                  # Exam paper JSON files
│   │   ├── exam-1.json
│   │   └── exam-2.json
│   ├── ansible/                # Grading playbooks + encrypted vault
│   └── frontend_dist/          # Vite build output (served by Flask)
│
├── frontend/                   # React + TypeScript exam UI
│   ├── App.tsx
│   ├── components/
│   │   ├── Instructions.tsx
│   │   ├── Terminal.tsx
│   │   └── VncPanel.tsx
│   └── services/
│
├── tests/                      # Pytest integration tests
├── setup.sh                    # Full one-shot setup script
├── teardown.sh                 # Destroy all VMs and clean state
└── run.sh                      # Start the platform (without rebuild)
```

---

## Teardown

To destroy all VMs, snapshots, and Terraform state:

```bash
./teardown.sh
```

> **Warning:** This permanently destroys all three VMs and their disk images. Packer artifacts in `packer/artifacts/` are preserved so a re-run of `setup.sh` won't need to rebuild from the ISO.

---

## Running Individual Scenarios

After the initial `setup.sh`, you can run specific scenarios directly:

```bash
# standard scenario, exam-2
./run.sh standard exam-2

# lvm scenario, exam-1 (default)
./run.sh lvm

# boot-menu scenario
./run.sh boot-menu exam-1
```

The `run.sh` script auto-restarts the Flask server if it exits unexpectedly.

---

## How It Works

<ol>
  <li><strong>Build</strong> — Packer boots the AlmaLinux ISO in a KVM VM, runs a fully automated Kickstart install, and saves the resulting qcow2 disk image to <code>packer/artifacts/</code>.</li>
  <li><strong>Deploy</strong> — Terraform clones the base image and defines the VM in libvirt with a fixed IP on <code>vm-network</code>.</li>
  <li><strong>Checkpoint</strong> — <code>virsh snapshot-create-as</code> creates a disk-only overlay, then <code>virsh save</code> captures a memory checkpoint. The VM can be restored to a pristine state in seconds.</li>
  <li><strong>Exam</strong> — Flask serves the React UI. The candidate sees a task list, a countdown timer, and a noVNC console connected directly to the VM.</li>
  <li><strong>Grading</strong> — On demand (or when time expires), the backend SSHs into the VM and runs Ansible playbooks that validate each task. Results are streamed back to the UI in real time.</li>
  <li><strong>Reset</strong> — After grading, the VM snapshot overlay is discarded and a fresh one is created, returning the VM to its initial state for the next attempt.</li>
</ol>
