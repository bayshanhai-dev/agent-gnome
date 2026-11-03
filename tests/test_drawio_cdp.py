#!/usr/bin/env python3
"""Acceptance test for Drawio through its visible renderer and CDP input."""

from __future__ import annotations

import os
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


EVIDENCE_DIR = Path(os.environ.get("TEST_EVIDENCE_DIR", Path(__file__).parent / "evidence"))
RUNTIME_DIR = Path(os.environ.get("AGENT_GNOME_RUNTIME_DIR", Path(__file__).parent / ".runtime"))


CDP_SCRIPT = r'''
import fs from "node:fs";

const port = Number(process.env.CDP_PORT);
const evidencePath = process.env.EVIDENCE_PATH;
const endpoint = `http://127.0.0.1:${port}`;

async function waitFor(description, predicate, timeout = 30000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const result = await predicate();
      if (result) return result;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${description}${lastError ? `: ${lastError}` : ""}`);
}

const target = await waitFor("a Drawio CDP page target", async () => {
  const response = await fetch(`${endpoint}/json/list`);
  const list = await response.json();
  return list.find((item) => item.type === "page");
}, 45000);

const ws = new WebSocket(target.webSocketDebuggerUrl);
let nextId = 1;
const pending = new Map();
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    pending.get(message.id)(message);
    pending.delete(message.id);
  }
};
await new Promise((resolve, reject) => {
  ws.onerror = () => reject(new Error("CDP WebSocket error"));
  ws.onopen = resolve;
});

function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, (message) => {
      if (message.error) reject(new Error(JSON.stringify(message.error)));
      else resolve(message);
    });
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const response = await call("Runtime.evaluate", { expression, returnByValue: true });
  if (response.result?.exceptionDetails) throw new Error(JSON.stringify(response.result.exceptionDetails));
  return response.result?.result?.value;
}

function mouse(type, x, y, button = "none", buttons = 0, clickCount = 1) {
  return call("Input.dispatchMouseEvent", { type, x, y, button, buttons, clickCount });
}

async function click(x, y) {
  await mouse("mousePressed", x, y, "left", 1);
  await mouse("mouseReleased", x, y, "left", 0);
}

async function doubleClick(x, y) {
  await mouse("mousePressed", x, y, "left", 1, 1);
  await mouse("mouseReleased", x, y, "left", 0, 1);
  await new Promise((resolve) => setTimeout(resolve, 80));
  await mouse("mousePressed", x, y, "left", 1, 2);
  await mouse("mouseReleased", x, y, "left", 0, 2);
}

await call("Page.enable");
const palette = JSON.parse(await waitFor("the rectangle palette item", async () => {
  const value = await evaluate(`JSON.stringify((() => {
    const items = Array.from(document.querySelectorAll("a.geItem"));
    const item = items.find((element) => {
      const box = element.getBoundingClientRect();
      const rect = element.querySelector("rect");
      return box.x < 60 && box.y > 200 && box.y < 500 && rect &&
        rect.getAttribute("width") === "28.8" && !rect.hasAttribute("rx");
    });
    if (!item) return null;
    const box = item.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  })())`);
  return value && value !== "null" ? value : null;
}, 45000));

const canvas = JSON.parse(await waitFor("the Drawio canvas", async () => {
  const value = await evaluate(`JSON.stringify((() => {
    const element = document.querySelector(".geDiagramContainer");
    if (!element) return null;
    const box = element.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  })())`);
  return value && value !== "null" ? value : null;
}, 45000));

const sourceX = palette.x + palette.width / 2;
const sourceY = palette.y + palette.height / 2;
const dropX = canvas.x + canvas.width * 0.50;
const dropY = canvas.y + canvas.height * 0.45;
await mouse("mouseMoved", sourceX, sourceY);
await mouse("mousePressed", sourceX, sourceY, "left", 1);
await mouse("mouseMoved", dropX - 180, dropY - 60, "none", 1);
await mouse("mouseMoved", dropX, dropY, "none", 1);
await mouse("mouseReleased", dropX, dropY, "left", 0);

const shape = JSON.parse(await waitFor("the dropped rectangle", async () => {
  const value = await evaluate(`JSON.stringify((() => {
    const canvas = document.querySelector(".geDiagramContainer").getBoundingClientRect();
    const candidates = Array.from(document.querySelectorAll(".geDiagramContainer svg rect"))
      .map((element) => { const box = element.getBoundingClientRect(); return {
        x: box.x, y: box.y, width: box.width, height: box.height,
        fill: element.getAttribute("fill") }; })
      .filter((box) => box.width >= 100 && box.height >= 50 && box.x >= canvas.x && box.y >= canvas.y);
    return candidates[0] || null;
  })())`);
  return value && value !== "null" ? value : null;
}, 15000));

const shapeX = shape.x + shape.width / 2;
const shapeY = shape.y + shape.height / 2;
await doubleClick(shapeX, shapeY);
await waitFor("the cell editor", async () => Boolean(await evaluate("Boolean(document.querySelector('.mxCellEditor'))")), 5000);
await call("Input.insertText", { text: "CDP GUI rectangle" });
await click(canvas.x + canvas.width - 80, canvas.y + canvas.height - 80);

const readback = await waitFor("the committed label in the canvas", async () => {
  const value = JSON.parse(await evaluate(`JSON.stringify((() => {
    const container = document.querySelector(".geDiagramContainer");
    const boxes = Array.from(container.querySelectorAll("svg rect")).map((element) => {
      const box = element.getBoundingClientRect();
      return { x: Math.round(box.x), y: Math.round(box.y), width: Math.round(box.width),
        height: Math.round(box.height), fill: element.getAttribute("fill") };
    }).filter((box) => box.width >= 100 && box.height >= 50);
    const labels = Array.from(container.querySelectorAll("svg foreignObject"))
      .map((element) => (element.textContent || "").trim()).filter(Boolean);
    return { shape: boxes[0] || null, labels,
      editorStillOpen: Boolean(document.querySelector(".mxCellEditor")),
      unsaved: document.body.innerText.includes("Unsaved changes") };
  })())`));
  return value.shape && value.labels.some((label) => label.includes("CDP GUI rectangle")) &&
    !value.editorStillOpen ? value : null;
}, 15000);

const screenshot = (await call("Page.captureScreenshot", { format: "png" })).result.data;
fs.writeFileSync(evidencePath, Buffer.from(screenshot, "base64"));
console.log(`DOM/UI readback: ${JSON.stringify(readback)}`);
console.log(`Evidence: ${evidencePath}`);
ws.close();
'''


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> int:
    drawio = shutil.which("drawio") or ("/usr/bin/drawio" if Path("/usr/bin/drawio").is_file() else None)
    if not drawio:
        print("Drawio CDP: SKIP: optional drawio executable is not installed")
        return 77
    if not shutil.which("node"):
        raise AssertionError("Node.js is required for the CDP test")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    evidence = EVIDENCE_DIR / "drawio-cdp.png"
    profile = Path(tempfile.mkdtemp(prefix="drawio-cdp-profile-", dir=RUNTIME_DIR))
    launch_log = RUNTIME_DIR / "drawio-cdp-launch.log"
    port = free_port()
    process = subprocess.Popen(
        [
            drawio,
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile}",
        ],
        stdout=launch_log.open("wb"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        environment = os.environ.copy()
        environment.update({"CDP_PORT": str(port), "EVIDENCE_PATH": str(evidence)})
        completed = subprocess.run(
            ["node", "--input-type=module", "-"],
            input=CDP_SCRIPT.encode(),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output = completed.stdout.decode(errors="replace")
        print(output, end="")
        if completed.returncode != 0:
            raise AssertionError(f"CDP interaction failed (exit {completed.returncode})")
        if not evidence.is_file() or evidence.stat().st_size == 0:
            raise AssertionError(f"CDP did not save evidence screenshot at {evidence}")
        print("Drawio CDP: PASS")
        return 0
    finally:
        stop_process(process)
        try:
            shutil.rmtree(profile)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"Drawio CDP: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
