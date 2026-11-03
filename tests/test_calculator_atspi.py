#!/usr/bin/env python3
"""Acceptance test for Calculator through the AT-SPI semantic layer."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

import pyatspi


EVIDENCE_DIR = Path(os.environ.get("TEST_EVIDENCE_DIR", Path(__file__).parent / "evidence"))


def descendants(node: object) -> Iterable[object]:
    yield node
    try:
        count = node.childCount  # type: ignore[attr-defined]
        for index in range(count):
            child = node.getChildAtIndex(index)  # type: ignore[attr-defined]
            if child is not None:
                yield from descendants(child)
    except Exception:
        return


def snapshot_nodes() -> list[object]:
    desktop = pyatspi.Registry.getDesktop(0)
    nodes: list[object] = []
    for index in range(desktop.childCount):
        app = desktop.getChildAtIndex(index)
        if app is not None:
            nodes.extend(descendants(app))
    return nodes


def desktop_app_names() -> list[str]:
    desktop = pyatspi.Registry.getDesktop(0)
    names: list[str] = []
    for index in range(desktop.childCount):
        app = desktop.getChildAtIndex(index)
        if app is not None and node_name(app):
            names.append(node_name(app))
    return names


def node_name(node: object) -> str:
    try:
        return str(node.name or "")  # type: ignore[attr-defined]
    except Exception:
        return ""


def role_name(node: object) -> str:
    try:
        return str(node.getRoleName() or "")  # type: ignore[attr-defined]
    except Exception:
        return ""


def find_named(names: set[str], timeout: float = 20.0) -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for node in snapshot_nodes():
            if node_name(node) in names and role_name(node) in {
                "push button",
                "toggle button",
                "button",
            }:
                return node
        time.sleep(0.1)
    named = sorted(
        (f"{role_name(node)}:{node_name(node)}" for node in snapshot_nodes() if node_name(node)),
        key=str,
    )
    sample = ", ".join(named[:80])
    raise AssertionError(
        f"AT-SPI control not found by accessible name: {sorted(names)}; "
        f"desktop apps: {desktop_app_names()}; named-node sample: {sample}"
    )


def activate(node: object, requested_names: set[str]) -> None:
    try:
        actions = node.queryAction()  # type: ignore[attr-defined]
        for index in range(actions.nActions):
            action_name = str(actions.getName(index) or "").lower()
            if action_name in {"click", "press", "activate"}:
                if not actions.doAction(index):
                    raise AssertionError(f"AT-SPI action failed for {sorted(requested_names)}")
                return
    except AssertionError:
        raise
    except Exception as exc:
        raise AssertionError(f"Could not activate {sorted(requested_names)} through AT-SPI: {exc}") from exc
    raise AssertionError(f"No click-like AT-SPI action exposed for {sorted(requested_names)}")


def text_values(node: object) -> list[str]:
    values: list[str] = []
    try:
        values.append(str(node.name or "").strip())  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        text = node.queryText().getText(0, -1)  # type: ignore[attr-defined]
        values.append(str(text).strip())
    except Exception:
        pass
    return [value for value in values if value]


def display_reads(value: str) -> bool:
    for node in snapshot_nodes():
        if role_name(node) not in {"entry", "label", "text", "panel"}:
            continue
        if value in text_values(node):
            return True
    return False


def wait_for_display(value: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if display_reads(value):
            return
        time.sleep(0.1)
    raise AssertionError(f"Calculator display did not read back {value!r} through AT-SPI")


def focus_calculator_window() -> bool:
    candidates = [
        node
        for node in snapshot_nodes()
        if role_name(node) == "frame" and "calculator" in node_name(node).lower()
    ]
    candidates.extend(node for node in snapshot_nodes() if node_name(node) == "=")
    for node in candidates:
        try:
            if node.queryComponent().grabFocus():  # type: ignore[attr-defined]
                return True
        except Exception:
            pass
    return False


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_attempt(attempt: int, runtime_dir: Path, app_environment: dict[str, str]) -> None:
    launch_log = runtime_dir / "calculator-launch.log"
    calculator = subprocess.Popen(
        ["gnome-calculator"],
        stdout=launch_log.open("wb"),
        stderr=subprocess.STDOUT,
        env=app_environment,
        start_new_session=True,
    )
    try:
        activate(find_named({"7"}), {"7"})
        activate(find_named({"×", "Multiply", "Multiplication"}), {"×", "Multiply", "Multiplication"})
        activate(find_named({"8"}), {"8"})
        activate(find_named({"="}), {"="})
        wait_for_display("56")
        focused = focus_calculator_window()
        time.sleep(0.5)
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        evidence = EVIDENCE_DIR / "calculator-atspi.png"
        # scrot otherwise invents a suffixed name when a prior run exists.
        evidence.unlink(missing_ok=True)
        completed = subprocess.run(["scrot", str(evidence)], check=False)
        if completed.returncode != 0 or not evidence.is_file() or evidence.stat().st_size == 0:
            raise AssertionError(f"Could not save Calculator evidence screenshot at {evidence}")
        print("Calculator AT-SPI: PASS")
        print(f"Evidence: {evidence}")
        if not focused:
            print("Warning: Calculator window could not be raised through AT-SPI; assertion still passed")
    finally:
        stop_process(calculator)


def main() -> int:
    runtime_dir = Path(os.environ.get("AGENT_GNOME_RUNTIME_DIR", Path(__file__).parent / ".runtime"))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    app_environment = os.environ.copy()
    # GTK 4 can otherwise leave its accessibility backend disabled in a
    # minimal headless session even though the GNOME desktop is accessible.
    app_environment["GTK_A11Y"] = "atspi"
    app_environment["NO_AT_BRIDGE"] = "0"
    app_environment["GDK_BACKEND"] = "x11"
    app_environment["GTK_MODULES"] = ":".join(
        value for value in [app_environment.get("GTK_MODULES", ""), "gail:atk-bridge"] if value
    )
    last_error: AssertionError | None = None
    for attempt in range(1, 4):
        try:
            run_attempt(attempt, runtime_dir, app_environment)
            return 0
        except AssertionError as exc:
            last_error = exc
            if attempt < 3:
                print(f"Calculator attempt {attempt} did not expose the controls yet; retrying", file=sys.stderr)
    assert last_error is not None
    raise last_error


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"Calculator AT-SPI: FAIL: {exc}", file=sys.stderr)
        launch_log = Path(os.environ.get("AGENT_GNOME_RUNTIME_DIR", Path(__file__).parent / ".runtime")) / "calculator-launch.log"
        if launch_log.is_file():
            print(f"Calculator launch log:\n{launch_log.read_text(errors='replace')[:4000]}", file=sys.stderr)
        raise SystemExit(1)
