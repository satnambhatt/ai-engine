#!/usr/bin/env bash
set -euo pipefail

# ══════════════════════════════════════════════════════════════
# Design Library Indexer — Pi Setup Script
# ══════════════════════════════════════════════════════════════
#
# Run this on a fresh Raspberry Pi 5 (64-bit OS Lite).
# It will:
#   1. Install system dependencies
#   2. Mount the USB drive
#   3. Create the directory structure
#   4. Install Ollama and pull models
#   5. Set up Python environment with adaptive worker auto-tuning
#   6. Install and enable systemd services
#
# Prerequisites:
#   Clone this repository first:
#     cd /home/rpi/ai-engine
#     git clone https://github.com/YOUR_USERNAME/design-library-indexer.git
#     cd design-library-indexer
#
# Usage:
#     chmod +x setup.sh
#     sudo ./setup.sh
#
# Features:
#   - Adaptive worker auto-tuning (40-70% faster indexing)
#   - Automatic thermal protection
#   - Resume support (stop/start anytime)
#   - Real-time file watching
#   - Nightly re-indexing
#
# ══════════════════════════════════════════════════════════════

LIBRARY_MOUNT="/mnt/design-library"
ENGINE_DIR="/home/rpi/ai-engine"
VENV_DIR="${ENGINE_DIR}/venv"

# Determine the script's directory (should be the cloned repo)
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INDEXER_DIR="${REPO_DIR}"

echo "═══════════════════════════════════════════════════"
echo "  Design Library Indexer — Setup"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Repository: ${REPO_DIR}"
echo "  Installing to: ${ENGINE_DIR}"
echo ""

# ── 1. System dependencies ──────────────────────────────────
echo ""
echo "[1/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl

# ── 2. Mount USB drive ──────────────────────────────────────
echo ""
echo "[2/6] Setting up USB drive mount..."
mkdir -p "${LIBRARY_MOUNT}"

# Detect USB drive (assumes it's the first USB block device)
USB_DEVICE=$(lsblk -dpno NAME,TRAN | grep usb | head -1 | awk '{print $1}')
if [ -z "${USB_DEVICE}" ]; then
    echo "  WARNING: No USB drive detected."
    echo "  Plug in your SSD and re-run, or manually add to /etc/fstab:"
    echo "  /dev/sdX1  ${LIBRARY_MOUNT}  ext4  defaults,noatime  0  2"
else
    PARTITION="${USB_DEVICE}1"
    if ! grep -q "${LIBRARY_MOUNT}" /etc/fstab; then
        UUID=$(blkid -s UUID -o value "${PARTITION}" 2>/dev/null || echo "")
        if [ -n "${UUID}" ]; then
            echo "UUID=${UUID}  ${LIBRARY_MOUNT}  ext4  defaults,noatime  0  2" >> /etc/fstab
            mount "${LIBRARY_MOUNT}" 2>/dev/null || true
            echo "  Mounted ${PARTITION} (UUID=${UUID}) at ${LIBRARY_MOUNT}"
        else
            echo "  WARNING: Could not determine UUID for ${PARTITION}."
            echo "  Please format the drive (ext4) and update /etc/fstab manually."
        fi
    else
        echo "  ${LIBRARY_MOUNT} already in fstab"
        mount "${LIBRARY_MOUNT}" 2>/dev/null || true
    fi
fi

# ── 3. Create directory structure ───────────────────────────
echo ""
echo "[3/6] Creating directory structure..."
mkdir -p "${LIBRARY_MOUNT}/example-websites/html-css"
mkdir -p "${LIBRARY_MOUNT}/example-websites/react"
mkdir -p "${LIBRARY_MOUNT}/example-websites/nextjs"
mkdir -p "${LIBRARY_MOUNT}/example-websites/astro"
mkdir -p "${LIBRARY_MOUNT}/example-websites/vue"
mkdir -p "${LIBRARY_MOUNT}/example-websites/svelte"
mkdir -p "${LIBRARY_MOUNT}/example-websites/tailwind"
mkdir -p "${LIBRARY_MOUNT}/example-websites/multi-page-sites"
mkdir -p "${LIBRARY_MOUNT}/components/headers"
mkdir -p "${LIBRARY_MOUNT}/components/hero-sections"
mkdir -p "${LIBRARY_MOUNT}/components/footers"
mkdir -p "${LIBRARY_MOUNT}/components/pricing-tables"
mkdir -p "${LIBRARY_MOUNT}/components/testimonials"
mkdir -p "${LIBRARY_MOUNT}/components/contact-forms"
mkdir -p "${LIBRARY_MOUNT}/components/cta-blocks"
mkdir -p "${LIBRARY_MOUNT}/components/feature-grids"
mkdir -p "${LIBRARY_MOUNT}/components/faq-accordions"
mkdir -p "${LIBRARY_MOUNT}/components/404-pages"
mkdir -p "${LIBRARY_MOUNT}/seo-configs/schema-templates"
mkdir -p "${LIBRARY_MOUNT}/seo-configs/meta-templates"
mkdir -p "${LIBRARY_MOUNT}/seo-configs/robots-templates"
mkdir -p "${LIBRARY_MOUNT}/style-guides/color-palettes"
mkdir -p "${LIBRARY_MOUNT}/style-guides/typography-systems"
mkdir -p "${LIBRARY_MOUNT}/style-guides/design-tokens"
mkdir -p "${LIBRARY_MOUNT}/client-projects"
mkdir -p "${LIBRARY_MOUNT}/.index"

chown -R rpi:rpi "${LIBRARY_MOUNT}"
echo "  Directory structure created."

# ── 4. Install Ollama + pull models ─────────────────────────
echo ""
echo "[4/6] Installing Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    echo "  Ollama installed."
else
    echo "  Ollama already installed."
fi

# Ensure Ollama is running
systemctl start ollama 2>/dev/null || ollama serve &>/dev/null &
sleep 3

echo "  Pulling embedding model (nomic-embed-text)..."
sudo -u rpi ollama pull nomic-embed-text

echo "  Pulling code generation model (qwen2.5-coder:3b)..."
sudo -u rpi ollama pull qwen2.5-coder:3b

echo "  Models ready."

# ── 5. Python environment ───────────────────────────────────
echo ""
echo "[5/6] Setting up Python environment..."

# Create logs directory
mkdir -p "${ENGINE_DIR}/logs"
chown -R rpi:rpi "${ENGINE_DIR}"

# Create virtual environment
if [ ! -d "${VENV_DIR}" ]; then
    sudo -u rpi python3 -m venv "${VENV_DIR}"
    echo "  Virtual environment created at ${VENV_DIR}"
else
    echo "  Virtual environment already exists at ${VENV_DIR}"
fi

# Install Python dependencies from the cloned repo
if [ -f "${INDEXER_DIR}/requirements.txt" ]; then
    echo "  Installing Python dependencies..."
    sudo -u rpi "${VENV_DIR}/bin/pip" install -q -r "${INDEXER_DIR}/requirements.txt"
    echo "  Dependencies installed."
else
    echo "  WARNING: requirements.txt not found in ${INDEXER_DIR}"
    echo "  Please ensure you're running this script from the cloned repository."
fi

# ── 6. systemd services & logrotate ─────────────────────────
echo ""
echo "[6/6] Installing systemd services..."

# Look for service files in the setup-ai-process subdirectory
SERVICE_DIR="${INDEXER_DIR}/setup-ai-process"

if [ -f "${SERVICE_DIR}/design-library-watcher.service" ]; then
    cp "${SERVICE_DIR}/design-library-watcher.service" /etc/systemd/system/
    cp "${SERVICE_DIR}/design-library-reindex.service" /etc/systemd/system/
    cp "${SERVICE_DIR}/design-library-reindex.timer" /etc/systemd/system/

    systemctl daemon-reload
    systemctl enable design-library-watcher
    systemctl enable design-library-reindex.timer

    echo "  ✅ Services installed and enabled"
else
    echo "  WARNING: systemd service files not found in ${SERVICE_DIR}"
    echo "  Please check repository structure."
fi

# Install logrotate configuration
if [ -f "${SERVICE_DIR}/design-library-logrotate" ]; then
    cp "${SERVICE_DIR}/design-library-logrotate" /etc/logrotate.d/design-library
    echo "  ✅ Logrotate configuration installed"
fi

# Verify documentation
echo ""
echo "  Verifying documentation..."

if [ -f "${INDEXER_DIR}/docs/README.md" ]; then
    echo "  ✅ Main documentation found"
fi

if [ -f "${INDEXER_DIR}/docs/adaptive_workers.md" ]; then
    echo "  ✅ Adaptive workers guide found"
fi

if [ -f "${INDEXER_DIR}/docs/design_decisions.md" ]; then
    echo "  ✅ Design decisions found"
fi

if [ -f "${INDEXER_DIR}/docs/implementation_summary.md" ]; then
    echo "  ✅ Implementation summary found"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Setup complete!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  📋 Next steps:"
echo ""
echo "  1. Clone design library examples:"
echo "     cd ${LIBRARY_MOUNT}/example-websites/html-css/"
echo "     git clone https://github.com/html5up/html5up.github.io html5up"
echo ""
echo "  2. Verify auto-tuning is active:"
echo "     cd ${INDEXER_DIR}"
echo "     ${VENV_DIR}/bin/python << 'EOF'"
echo "from indexer.autotune import choose_worker_count, get_system_metrics"
echo "metrics = get_system_metrics()"
echo "workers = choose_worker_count()"
echo "print(f'✅ Auto-Tuning Active: {workers} workers')"
echo "print(f'   Load: {metrics[\"load_avg\"]:.1f}/{metrics[\"cpu_cores\"]} cores')"
echo "print(f'   Temp: {metrics[\"temp_c\"]:.0f}°C')"
echo "EOF"
echo ""
echo "  3. Run your first index (with adaptive workers):"
echo "     cd ${INDEXER_DIR}"
echo "     ${VENV_DIR}/bin/python run_indexer.py index --full -v"
echo ""
echo "  4. Monitor auto-tuning (in another terminal):"
echo "     tail -f ${ENGINE_DIR}/logs/indexer-manual.log | grep 'Auto-tune'"
echo ""
echo "  5. Test semantic search:"
echo "     ${VENV_DIR}/bin/python run_indexer.py search 'hero section with gradient'"
echo ""
echo "  6. Start the file watcher service:"
echo "     sudo systemctl start design-library-watcher"
echo "     journalctl -u design-library-watcher -f"
echo ""
echo "  7. Enable nightly re-index:"
echo "     sudo systemctl start design-library-reindex.timer"
echo ""
echo "  📚 Documentation:"
echo "     ${INDEXER_DIR}/docs/README.md - Main documentation"
echo "     ${INDEXER_DIR}/docs/adaptive_workers.md - Auto-tuning guide"
echo "     ${INDEXER_DIR}/docs/design_decisions.md - Architecture details"
echo "     ${INDEXER_DIR}/docs/implementation_summary.md - Quick reference"
echo ""
