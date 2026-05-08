#!/bin/sh
# .pylab/setup.sh — constraint repo pylab setup
set -e

REQUIRED="9.1.12"
TARGET_VERSION="10.0.2"

echo "[setup] Checking for existing SWI-Prolog installation..."
if command -v swipl >/dev/null 2>&1; then
    VERSION=$(swipl --version | grep -oP 'version \K[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    if [ "$(printf '%s\n' "$REQUIRED" "$VERSION" | sort -V | head -n1)" = "$REQUIRED" ]; then
        echo "[setup] SWI-Prolog $VERSION is already installed and satisfies >= $REQUIRED."
        echo "[setup] Skipping build."
        exit 0
    fi
    echo "[setup] Existing SWI-Prolog is $VERSION, which is too old. Rebuilding..."
fi

echo "[setup] Installing SWI-Prolog dependencies"
apt-get update -qq
apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build \
    git zlib1g-dev libgmp-dev libssl-dev \
    libreadline-dev libedit-dev

# Ensure clean slate before cloning
echo "[setup] Cleaning up any previous build directories..."
rm -rf /tmp/swipl

# Clone the STABLE repository
echo "[setup] Cloning SWI-Prolog V${TARGET_VERSION}..."
git clone --branch V${TARGET_VERSION} --depth 1 https://github.com/SWI-Prolog/swipl.git /tmp/swipl
cd /tmp/swipl
git submodule update --init --recursive

# Build and install (Skipping documentation to avoid man/archive errors)
echo "[setup] Building SWI-Prolog..."
mkdir build && cd build
cmake -G Ninja -DCMAKE_BUILD_TYPE=Release -DINSTALL_DOCUMENTATION=OFF ..
ninja
ninja install

# Cleanup after successful build
cd /
rm -rf /tmp/swipl

echo "[setup] Verifying new SWI-Prolog version"
VERSION=$(swipl --version | grep -oP 'version \K[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ "$(printf '%s\n' "$REQUIRED" "$VERSION" | sort -V | head -n1)" != "$REQUIRED" ]; then
    echo "[setup] ERROR: SWI-Prolog $VERSION is too old (need >= $REQUIRED)"
    exit 1
fi
echo "[setup] SWI-Prolog $VERSION OK"
