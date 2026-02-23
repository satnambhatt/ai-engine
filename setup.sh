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
#     cd /home/<your-user>/ai-engine
#     git clone https://github.com/YOUR_USERNAME/design-library-indexer.git
#     cd design-library-indexer
#
# Usage:
#     chmod +x setup.sh
#     sudo ./setup.sh                  # Full setup (deps, Ollama, Python, services)
#     sudo ./setup.sh --services-only  # Only install/configure systemd services
#
# Features:
#   - Adaptive worker auto-tuning (40-70% faster indexing)
#   - Automatic thermal protection
#   - Resume support (stop/start anytime)
#   - Real-time file watching
#   - Nightly re-indexing
#
# ══════════════════════════════════════════════════════════════

# Determine the actual (non-root) user who invoked this script
if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
    ACTUAL_USER="${SUDO_USER}"
elif [ -n "${USER:-}" ] && [ "${USER}" != "root" ]; then
    ACTUAL_USER="${USER}"
else
    ACTUAL_USER=$(logname 2>/dev/null || true)
    if [ -z "${ACTUAL_USER}" ] || [ "${ACTUAL_USER}" = "root" ]; then
        echo "ERROR: Could not determine a non-root user."
        echo "  Run as: sudo ./setup.sh  (from a non-root account)"
        echo "  Or set: sudo ACTUAL_USER=youruser ./setup.sh"
        exit 1
    fi
fi

# ── Parse flags ──────────────────────────────────────────────
SERVICES_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --services-only) SERVICES_ONLY=true ;;
        --help|-h)
            echo "Usage: sudo ./setup.sh [--services-only]"
            echo "  (default)         Full setup: deps, Ollama, Python env, services"
            echo "  --services-only   Only install/configure systemd services"
            exit 0 ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

USER_HOME=$(eval echo "~${ACTUAL_USER}")
ENGINE_DIR="${USER_HOME}/ai-engine"
VENV_DIR="${ENGINE_DIR}/venv"
ENV_FILE="${ENGINE_DIR}/.env"

# Determine the script's directory (should be the cloned repo)
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INDEXER_DIR="${REPO_DIR}"

# ── Wait for dpkg/apt lock ───────────────────────────────────
wait_for_apt_lock() {
    local lock_files=("/var/lib/dpkg/lock-frontend" "/var/lib/dpkg/lock" "/var/lib/apt/lists/lock")
    local timeout=300
    local elapsed=0
    for lock_file in "${lock_files[@]}"; do
        while ! flock -n "${lock_file}" /bin/true 2>/dev/null; do
            if [ ${elapsed} -ge ${timeout} ]; then
                echo "  ERROR: apt/dpkg lock held for over ${timeout}s. Try: sudo kill $(lsof -t ${lock_file} 2>/dev/null) or reboot."
                exit 1
            fi
            echo "  apt/dpkg is locked by another process. Waiting... (${elapsed}s elapsed)"
            sleep 5
            elapsed=$((elapsed + 5))
        done
    done
}

echo "═══════════════════════════════════════════════════"
echo "  Design Library Indexer — Setup"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Repository: ${REPO_DIR}"
echo "  Installing to: ${ENGINE_DIR}"
echo "  Mode: $( [ "${SERVICES_ONLY}" = "true" ] && echo "services only" || echo "full setup" )"
echo ""

if [ "${SERVICES_ONLY}" != "true" ]; then

# ── Storage mode — ask user before anything else ─────────────
echo "─────────────────────────────────────────────────────"
echo "  Storage configuration"
echo "─────────────────────────────────────────────────────"
echo ""

if [ -f "${ENV_FILE}" ]; then
    # .env already exists — show current settings and ask whether to keep them
    echo "  Existing configuration found at ${ENV_FILE}:"
    grep -v '^#' "${ENV_FILE}" | grep '=' | sed 's/^/    /'
    echo ""
    read -r -p "  Keep existing storage configuration? [Y/n]: " KEEP_ENV
    KEEP_ENV="${KEEP_ENV:-Y}"
    if [[ "${KEEP_ENV}" =~ ^[Yy] ]]; then
        # Source the existing .env
        set -o allexport; source "${ENV_FILE}"; set +o allexport
        USE_EXTERNAL_DRIVE="${USE_EXTERNAL_DRIVE:-false}"
        LIBRARY_ROOT="${LIBRARY_ROOT:-${ENGINE_DIR}/design-library}"
        CHROMA_DIR="${CHROMA_DIR:-${ENGINE_DIR}/chroma_data}"
        echo "  Using existing configuration."
    else
        rm -f "${ENV_FILE}"
    fi
fi

if [ ! -f "${ENV_FILE}" ]; then
    read -r -p "  Do you have an external USB drive for the design library? [Y/n]: " DRIVE_ANSWER
    DRIVE_ANSWER="${DRIVE_ANSWER:-Y}"

    if [[ "${DRIVE_ANSWER}" =~ ^[Yy] ]]; then
        USE_EXTERNAL_DRIVE=true
        LIBRARY_ROOT="/mnt/design-library"
        CHROMA_DIR="/mnt/design-library/chroma_data"
        echo "  External drive selected — library: ${LIBRARY_ROOT}"
    else
        USE_EXTERNAL_DRIVE=false
        LIBRARY_ROOT="${ENGINE_DIR}/design-library"
        CHROMA_DIR="${ENGINE_DIR}/chroma_data"
        echo "  Local storage selected — library: ${LIBRARY_ROOT}"
    fi

    # Write .env so all components pick up the same storage mode
    cat > "${ENV_FILE}" <<EOF
# AI Engine — Storage Configuration
# Generated by setup.sh — edit to change storage mode then restart services.
USE_EXTERNAL_DRIVE=${USE_EXTERNAL_DRIVE}
LIBRARY_ROOT=${LIBRARY_ROOT}
CHROMA_DIR=${CHROMA_DIR}
EOF
    echo "  Written: ${ENV_FILE}"
fi
echo ""

# ── 1. System dependencies ──────────────────────────────────
echo ""
echo "[1/6] Installing system dependencies..."
wait_for_apt_lock
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl

# ── 2. Mount USB drive (external drive only) ────────────────
echo ""
echo "[2/6] Setting up storage..."

if [ "${USE_EXTERNAL_DRIVE}" = "true" ]; then
    # Check if already mounted or in fstab
    if grep -q "${LIBRARY_ROOT}" /etc/fstab; then
        echo "  ${LIBRARY_ROOT} already in fstab"
        mount "${LIBRARY_ROOT}" 2>/dev/null || true
        echo "  Mount already configured."
    else
        mkdir -p "${LIBRARY_ROOT}"

        # Detect USB drive (assumes it's the first USB block device)
        USB_DEVICE=$(lsblk -dpno NAME,TRAN | grep usb | head -1 | awk '{print $1}')
        if [ -z "${USB_DEVICE}" ]; then
            echo "  WARNING: No USB drive detected."
            echo "  Plug in your SSD and re-run, or manually add to /etc/fstab:"
            echo "  /dev/sdX1  ${LIBRARY_ROOT}  ext4  defaults,noatime  0  2"
        else
            PARTITION="${USB_DEVICE}1"
            UUID=$(blkid -s UUID -o value "${PARTITION}" 2>/dev/null || echo "")
            if [ -n "${UUID}" ]; then
                echo "UUID=${UUID}  ${LIBRARY_ROOT}  ext4  defaults,noatime  0  2" >> /etc/fstab
                mount "${LIBRARY_ROOT}" 2>/dev/null || true
                echo "  Mounted ${PARTITION} (UUID=${UUID}) at ${LIBRARY_ROOT}"
            else
                echo "  WARNING: Could not determine UUID for ${PARTITION}."
                echo "  Please format the drive (ext4) and update /etc/fstab manually."
            fi
        fi
    fi
else
    echo "  Local storage mode — skipping USB mount."
    mkdir -p "${LIBRARY_ROOT}"
    echo "  Created local library directory: ${LIBRARY_ROOT}"
fi

# ── 3. Create directory structure ───────────────────────────
echo ""
echo "[3/6] Creating directory structure..."

# Check if directory structure already exists
if [ -d "${LIBRARY_ROOT}/components" ] && [ -d "${LIBRARY_ROOT}/example-websites" ]; then
    echo "  Directory structure already exists."
else
    mkdir -p "${LIBRARY_ROOT}/example-websites/html-css"
    mkdir -p "${LIBRARY_ROOT}/example-websites/react"
    mkdir -p "${LIBRARY_ROOT}/example-websites/nextjs"
    mkdir -p "${LIBRARY_ROOT}/example-websites/astro"
    mkdir -p "${LIBRARY_ROOT}/example-websites/vue"
    mkdir -p "${LIBRARY_ROOT}/example-websites/svelte"
    mkdir -p "${LIBRARY_ROOT}/example-websites/tailwind"
    mkdir -p "${LIBRARY_ROOT}/example-websites/multi-page-sites"
    mkdir -p "${LIBRARY_ROOT}/components/headers"
    mkdir -p "${LIBRARY_ROOT}/components/hero-sections"
    mkdir -p "${LIBRARY_ROOT}/components/footers"
    mkdir -p "${LIBRARY_ROOT}/components/pricing-tables"
    mkdir -p "${LIBRARY_ROOT}/components/testimonials"
    mkdir -p "${LIBRARY_ROOT}/components/contact-forms"
    mkdir -p "${LIBRARY_ROOT}/components/cta-blocks"
    mkdir -p "${LIBRARY_ROOT}/components/feature-grids"
    mkdir -p "${LIBRARY_ROOT}/components/faq-accordions"
    mkdir -p "${LIBRARY_ROOT}/components/404-pages"
    mkdir -p "${LIBRARY_ROOT}/seo-configs/schema-templates"
    mkdir -p "${LIBRARY_ROOT}/seo-configs/meta-templates"
    mkdir -p "${LIBRARY_ROOT}/seo-configs/robots-templates"
    mkdir -p "${LIBRARY_ROOT}/style-guides/color-palettes"
    mkdir -p "${LIBRARY_ROOT}/style-guides/typography-systems"
    mkdir -p "${LIBRARY_ROOT}/style-guides/design-tokens"
    mkdir -p "${LIBRARY_ROOT}/client-projects"
    mkdir -p "${LIBRARY_ROOT}/.index"
    mkdir -p "${CHROMA_DIR}"
    echo "  Directory structure created."
fi

chown -R "${ACTUAL_USER}:${ACTUAL_USER}" "${LIBRARY_ROOT}"
mkdir -p "${CHROMA_DIR}" && chown -R "${ACTUAL_USER}:${ACTUAL_USER}" "${CHROMA_DIR}"

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
sudo -u "${ACTUAL_USER}" ollama pull nomic-embed-text

echo "  Pulling code generation model (qwen2.5-coder:3b)..."
sudo -u "${ACTUAL_USER}" ollama pull qwen2.5-coder:3b

echo "  Models ready."

# ── 5. Python environment ───────────────────────────────────
echo ""
echo "[5/6] Setting up Python environment..."

# Create logs directory
mkdir -p "${ENGINE_DIR}/logs"
chown -R "${ACTUAL_USER}:${ACTUAL_USER}" "${ENGINE_DIR}"

# Create virtual environment
if [ ! -d "${VENV_DIR}" ]; then
    sudo -u "${ACTUAL_USER}" python3 -m venv "${VENV_DIR}"
    echo "  Virtual environment created at ${VENV_DIR}"
else
    echo "  Virtual environment already exists at ${VENV_DIR}"
fi

# Install Python dependencies from the cloned repo
if [ -f "${INDEXER_DIR}/requirements.txt" ]; then
    echo "  Installing Python dependencies..."
    sudo -u "${ACTUAL_USER}" "${VENV_DIR}/bin/pip" install -q -r "${INDEXER_DIR}/requirements.txt"
    echo "  Dependencies installed."
else
    echo "  WARNING: requirements.txt not found in ${INDEXER_DIR}"
    echo "  Please ensure you're running this script from the cloned repository."
fi

fi  # end SERVICES_ONLY check

# ── 6. systemd services & logrotate ─────────────────────────
echo ""
echo "[6/6] Installing systemd services..."

# Look for service files in the setup-ai-process subdirectory
SERVICE_DIR="${INDEXER_DIR}/setup-ai-process"

if [ -f "${SERVICE_DIR}/design-library-watcher.service" ]; then
    # Show current service status before asking
    WATCHER_INSTALLED=false
    WATCHER_ENABLED=false
    TIMER_ENABLED=false
    if [ -f "/etc/systemd/system/design-library-watcher.service" ]; then
        WATCHER_INSTALLED=true
        systemctl is-enabled design-library-watcher &>/dev/null && WATCHER_ENABLED=true || true
        systemctl is-enabled design-library-reindex.timer &>/dev/null && TIMER_ENABLED=true || true
    fi

    echo ""
    echo "  Current service status:"
    if [ "${WATCHER_INSTALLED}" = "true" ]; then
        WATCHER_STATE=$(systemctl is-active design-library-watcher 2>/dev/null || echo "inactive")
        TIMER_STATE=$(systemctl is-active design-library-reindex.timer 2>/dev/null || echo "inactive")
        echo "    design-library-watcher:       installed  (enabled: ${WATCHER_ENABLED}, active: ${WATCHER_STATE})"
        echo "    design-library-reindex.timer: installed  (enabled: ${TIMER_ENABLED}, active: ${TIMER_STATE})"
    else
        echo "    No services installed yet."
    fi
    echo ""

    # Prompt to install/reinstall service files
    read -r -p "  Install (or reinstall) systemd service files? [Y/n]: " INSTALL_SERVICES
    INSTALL_SERVICES="${INSTALL_SERVICES:-Y}"

    if [[ "${INSTALL_SERVICES}" =~ ^[Yy] ]]; then
        # Substitute AI_ENGINE_USER placeholder with the actual user
        sed -e "s|AI_ENGINE_USER|${ACTUAL_USER}|g" \
            "${SERVICE_DIR}/design-library-watcher.service" \
            > /etc/systemd/system/design-library-watcher.service
        sed -e "s|AI_ENGINE_USER|${ACTUAL_USER}|g" \
            "${SERVICE_DIR}/design-library-reindex.service" \
            > /etc/systemd/system/design-library-reindex.service
        cp "${SERVICE_DIR}/design-library-reindex.timer" /etc/systemd/system/

        systemctl daemon-reload
        echo "  ✅ Service files installed"

        # Prompt to enable on boot
        read -r -p "  Enable services to start on boot? [y/N]: " ENABLE_ANSWER
        ENABLE_ANSWER="${ENABLE_ANSWER:-N}"
        if [[ "${ENABLE_ANSWER}" =~ ^[Yy] ]]; then
            systemctl enable design-library-watcher
            systemctl enable design-library-reindex.timer
            echo "  ✅ Services enabled (will start on next boot)"
        else
            echo "  Services installed but not enabled on boot."
            echo "  To enable later: sudo systemctl enable design-library-watcher design-library-reindex.timer"
        fi

        # Prompt to start now
        read -r -p "  Start services now? [y/N]: " START_ANSWER
        START_ANSWER="${START_ANSWER:-N}"
        if [[ "${START_ANSWER}" =~ ^[Yy] ]]; then
            systemctl start design-library-watcher
            systemctl start design-library-reindex.timer
            echo "  ✅ Services started"
            echo "  Monitor: journalctl -u design-library-watcher -f"
        else
            echo "  Services not started. To start manually:"
            echo "    sudo systemctl start design-library-watcher"
            echo "    sudo systemctl start design-library-reindex.timer"
        fi
    else
        echo "  Skipping service installation."
    fi
else
    echo "  WARNING: systemd service files not found in ${SERVICE_DIR}"
    echo "  Please check repository structure."
fi

# Install logrotate configuration
if [ -f "${SERVICE_DIR}/design-library-logrotate" ]; then
    sed -e "s|AI_ENGINE_DIR|${ENGINE_DIR}|g" \
        -e "s|AI_ENGINE_USER|${ACTUAL_USER}|g" \
        "${SERVICE_DIR}/design-library-logrotate" \
        > /etc/logrotate.d/design-library
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
echo "     cd ${LIBRARY_ROOT}/example-websites/html-css/"
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
