#!/usr/bin/env bash
set -u
set -o pipefail

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TEST_DIR="$ROOT_DIR/tests"
EVIDENCE_DIR="$TEST_DIR/evidence"
RUNTIME_DIR=${AGENT_GNOME_RUNTIME_DIR:-"$ROOT_DIR/.tests-runtime"}
mkdir -p "$EVIDENCE_DIR" "$RUNTIME_DIR"

started_xvfb=0
xvfb_pid=""

cleanup_outer() {
    if [ -n "$xvfb_pid" ] && kill -0 "$xvfb_pid" 2>/dev/null; then
        kill "$xvfb_pid" 2>/dev/null || true
        wait "$xvfb_pid" 2>/dev/null || true
    fi
}
trap cleanup_outer EXIT

if [ -z "${DISPLAY:-}" ] || ! command -v xdpyinfo >/dev/null 2>&1 || ! xdpyinfo >/dev/null 2>&1; then
    if ! command -v Xvfb >/dev/null 2>&1; then
        echo "GNOME GUI suite: FAIL (Xvfb is required when no usable DISPLAY exists)"
        exit 1
    fi
    display_number=94
    while [ "$display_number" -lt 120 ] && [ -e "/tmp/.X11-unix/X$display_number" ]; do
        display_number=$((display_number + 1))
    done
    if [ "$display_number" -ge 120 ]; then
        echo "GNOME GUI suite: FAIL (no free headless display found)"
        exit 1
    fi
    export DISPLAY=":$display_number"
    Xvfb "$DISPLAY" -screen 0 1600x1000x24 >"$RUNTIME_DIR/xvfb.log" 2>&1 &
    xvfb_pid=$!
    started_xvfb=1
    for _ in $(seq 1 50); do
        if xdpyinfo >/dev/null 2>&1; then break; fi
        sleep 0.1
    done
    if ! xdpyinfo >/dev/null 2>&1; then
        echo "GNOME GUI suite: FAIL (Xvfb did not become ready)"
        exit 1
    fi
fi

run_tests() {
    local gnome_pid=""
    local gnome_launcher_pid=""
    local started_gnome=0
    local -a results=()
    local pass_count=0 fail_count=0 skip_count=0

    cleanup_gnome() {
        local pid=$1
        local started=$2
        if [ "$started" -eq 1 ] && [ -n "$pid" ] && [ "$pid" != "$$" ] && kill -0 "$pid" 2>/dev/null; then
            kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
            for _ in $(seq 1 40); do
                if ! kill -0 "$pid" 2>/dev/null; then break; fi
                sleep 0.1
            done
            kill -KILL -- -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
        fi
    }

    session_bus_ready() {
        command -v gdbus >/dev/null 2>&1 && \
            gdbus introspect --session \
                --dest org.gnome.SessionManager \
                --object-path /org/gnome/SessionManager >/dev/null 2>&1
    }

    accessibility_shell_ready() {
        timeout 1s python3 - <<'PY' >/dev/null 2>&1
import pyatspi
desktop = pyatspi.Registry.getDesktop(0)
names = []
for index in range(desktop.childCount):
    app = desktop.getChildAtIndex(index)
    if app is not None:
        names.append((app.name or "").lower())
raise SystemExit(0 if any("gnome-shell" in name or name == "gnome shell" for name in names) else 1)
PY
    }

    if ! session_bus_ready; then
        if ! command -v gnome-session >/dev/null 2>&1; then
            echo "GNOME GUI suite: FAIL (gnome-session is required)"
            return 1
        fi
        gnome_pid_file="$RUNTIME_DIR/gnome-session.pid"
        rm -f "$gnome_pid_file"
        setsid bash -c 'printf "%s\\n" "$$" > "$1"; exec gnome-session --session=ubuntu' \
            -- "$gnome_pid_file" >"$RUNTIME_DIR/gnome-session.log" 2>&1 &
        gnome_launcher_pid=$!
        started_gnome=1
        for _ in $(seq 1 40); do
            if [ -s "$gnome_pid_file" ]; then
                gnome_pid=$(sed -n '1p' "$gnome_pid_file")
                break
            fi
            sleep 0.1
        done
        if [ -z "$gnome_pid" ]; then
            echo "GNOME GUI suite: FAIL (could not identify the GNOME session process)"
            kill "$gnome_launcher_pid" 2>/dev/null || true
            return 1
        fi
        # Wait for the session manager on this D-Bus, not a similarly named
        # process left over from another display or session.
        for _ in $(seq 1 120); do
            if session_bus_ready; then
                break
            fi
            sleep 0.25
        done
        if ! session_bus_ready; then
            echo "GNOME GUI suite: FAIL (GNOME session manager did not become ready)"
            cleanup_gnome "$gnome_pid" "$started_gnome"
            return 1
        fi
    fi

    for _ in $(seq 1 80); do
        if accessibility_shell_ready; then
            break
        fi
        sleep 0.25
    done
    if ! accessibility_shell_ready; then
        echo "GNOME GUI suite: FAIL (GNOME Shell was not exposed through AT-SPI)"
        cleanup_gnome "$gnome_pid" "$started_gnome"
        return 1
    fi
    if command -v gsettings >/dev/null 2>&1; then
        gsettings set org.gnome.desktop.interface toolkit-accessibility true >/dev/null 2>&1 || true
    fi

    run_one() {
        local label=$1
        local script=$2
        local log="$RUNTIME_DIR/$label.log"
        local status
        set +e
        TEST_EVIDENCE_DIR="$EVIDENCE_DIR" AGENT_GNOME_RUNTIME_DIR="$RUNTIME_DIR" \
            python3 "$TEST_DIR/$script" >"$log" 2>&1
        status=$?
        set -e
        case "$status" in
            0)
                results+=("$label: PASS")
                pass_count=$((pass_count + 1))
                ;;
            77)
                results+=("$label: SKIP")
                skip_count=$((skip_count + 1))
                ;;
            *)
                results+=("$label: FAIL")
                fail_count=$((fail_count + 1))
                echo "--- $label output ---"
                sed -n '1,240p' "$log"
                ;;
        esac
    }

    run_one calculator-atspi test_calculator_atspi.py
    run_one drawio-cdp test_drawio_cdp.py

    echo "GNOME GUI suite summary"
    printf '%s\n' "${results[@]}"
    echo "Totals: PASS=$pass_count FAIL=$fail_count SKIP=$skip_count"

    cleanup_gnome "$gnome_pid" "$started_gnome"
    [ "$fail_count" -eq 0 ]
}

if [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    run_tests
else
    dbus-run-session -- bash -c 'run_tests() { :; }; exec bash "$1"' -- "$0"
fi
