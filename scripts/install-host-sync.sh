#!/bin/bash
# install-host-sync.sh — Set up host timezone sync from Home Assistant
#
# This script installs a systemd timer that keeps the host OS timezone
# in sync with the Local Timezone integration in Home Assistant.
#
# The integration writes the current timezone to a file inside the
# HASS config directory. This timer reads that file and applies it.
#
# Run as root (or with sudo) on the machine running Home Assistant.

set -e

SERVICE_NAME="hass-timezone-sync"
TZ_FILENAME=".local_timezone"

echo "=== Home Assistant Local Timezone — Host Sync Setup ==="
echo

# --- Find the HASS config directory ---

HASS_CONFIG=""

# Try to find it via Docker
if command -v docker &>/dev/null; then
    for name in home-assistant homeassistant hass; do
        MOUNT=$(docker inspect "$name" 2>/dev/null \
            | python3 -c "
import json, sys
try:
    c = json.load(sys.stdin)
    for m in c[0].get('Mounts', []):
        if m.get('Destination') == '/config':
            print(m['Source'])
            break
except: pass
" 2>/dev/null)
        if [ -n "$MOUNT" ]; then
            HASS_CONFIG="$MOUNT"
            echo "Found HASS config via Docker container '$name': $HASS_CONFIG"
            break
        fi
    done
fi

# Try common paths if Docker didn't work
if [ -z "$HASS_CONFIG" ]; then
    for path in \
        /usr/share/hassio/homeassistant \
        /home/homeassistant/.homeassistant \
        /root/.homeassistant \
        /config \
        /var/lib/hass; do
        if [ -f "$path/configuration.yaml" ]; then
            HASS_CONFIG="$path"
            echo "Found HASS config at: $HASS_CONFIG"
            break
        fi
    done
fi

# Ask the user if we still can't find it
if [ -z "$HASS_CONFIG" ]; then
    echo "Could not auto-detect Home Assistant config directory."
    echo
    read -rp "Enter the path to your HASS config directory: " HASS_CONFIG
fi

# Validate
TZ_FILE="$HASS_CONFIG/$TZ_FILENAME"
if [ ! -d "$HASS_CONFIG" ]; then
    echo "ERROR: Directory does not exist: $HASS_CONFIG"
    exit 1
fi

if [ -f "$TZ_FILE" ]; then
    echo "Timezone file already exists: $(cat "$TZ_FILE")"
else
    echo "Note: Timezone file not found yet. It will be created when the"
    echo "      Local Timezone integration updates. Continuing setup."
fi

echo

# --- Install systemd units ---

cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Sync system timezone from Home Assistant
After=network.target docker.service

[Service]
Type=oneshot
ExecStart=/bin/bash -c '\\
    TZ_FILE="${TZ_FILE}"; \\
    if [ ! -f "\$TZ_FILE" ]; then exit 0; fi; \\
    NEW_TZ=\$(cat "\$TZ_FILE" | tr -d "\\n\\r "); \\
    if [ -z "\$NEW_TZ" ]; then exit 0; fi; \\
    CURRENT_TZ=\$(timedatectl show -p Timezone --value 2>/dev/null); \\
    if [ "\$NEW_TZ" = "\$CURRENT_TZ" ]; then exit 0; fi; \\
    timedatectl set-timezone "\$NEW_TZ" && \\
    logger -t hass-tz-sync "Timezone updated: \$CURRENT_TZ -> \$NEW_TZ"'
EOF

cat > /etc/systemd/system/${SERVICE_NAME}.timer << EOF
[Unit]
Description=Check Home Assistant timezone every 15 minutes

[Timer]
OnBootSec=60
OnUnitActiveSec=900
AccuracySec=60

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ${SERVICE_NAME}.timer

echo
echo "=== Setup complete! ==="
echo
echo "  Timer:   ${SERVICE_NAME}.timer (every 15 minutes)"
echo "  Service: ${SERVICE_NAME}.service"
echo "  File:    ${TZ_FILE}"
echo
echo "Check status:  systemctl status ${SERVICE_NAME}.timer"
echo "Manual run:    systemctl start ${SERVICE_NAME}.service"
echo "View logs:     journalctl -t hass-tz-sync"
echo
echo "The system timezone will sync automatically when the"
echo "Local Timezone integration writes to ${TZ_FILE}."
