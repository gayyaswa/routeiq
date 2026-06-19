#!/usr/bin/env python3
"""
Generate docs/demo.gif — RouteIQ animated demo.

Captures: hint buttons → click demo route → stepper progression
          (parse→graph→rag→narrate with streaming text) → map + stop cards → narrative.

Usage:
    python3 scripts/generate_demo_gif.py
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"
PORT = 8502  # use a side port to avoid colliding with a running dev server
URL = f"http://localhost:{PORT}"
OUT_PATH = DOCS / "demo.gif"

# Demo route to click — Muir Woods is the fastest Bay Area cached route
DEMO_BUTTON_TEXT = "Muir Woods"


# ── helpers ──────────────────────────────────────────────────────────────────

def _wait_for_server(timeout: int = 120) -> bool:
    import requests as _req
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if _req.get(URL, timeout=3).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _make_gif(screenshots: list[tuple[bytes, int]]) -> None:
    from PIL import Image

    frames: list[Image.Image] = []
    durations: list[int] = []
    for png_bytes, ms in screenshots:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        frames.append(img.quantize(colors=256))
        durations.append(ms)

    if not frames:
        sys.exit("No frames captured — aborting")

    DOCS.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUT_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"\n✅  {OUT_PATH}  ({OUT_PATH.stat().st_size / 1024:.0f} KB, {len(frames)} frames)")


# ── browser recording ─────────────────────────────────────────────────────────

def _record() -> None:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        sys.exit("playwright missing — run: pip install playwright && playwright install chromium")

    screenshots: list[tuple[bytes, int]] = []  # (png_bytes, frame_duration_ms)

    def snap(page, ms: int = 2500) -> None:
        screenshots.append((page.screenshot(), ms))
        print(f"    📸  frame {len(screenshots)}  ({ms} ms)")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(URL, wait_until="networkidle")

        # ── Frame 1: initial load — Tab 1 (Day Trip Planner) ────────────
        print("  Waiting for app title to render…")
        try:
            page.wait_for_selector("h1:has-text('RouteIQ')", timeout=30_000)
        except Exception:
            print("  WARNING: title not found, waiting anyway")
        page.wait_for_timeout(3000)
        snap(page, 3000)

        # ── Wait for bg-init banner to clear ─────────────────────────────
        print("  Waiting for background init to finish…")
        try:
            page.wait_for_selector(
                "text=Loading RouteIQ components", state="hidden", timeout=60_000
            )
            print("  ✅ Background init complete")
        except Exception:
            print("  NOTE: bg-init banner gone or timed out, continuing")
        print("  Waiting for pre-warm (LLM + ChromaDB)…")
        page.wait_for_timeout(15_000)
        print("  ✅ Pre-warm wait complete")

        # ── Frame 2: Day Trip Planner form ready ─────────────────────────
        snap(page, 3000)

        # ── Switch to Tab 2 (Route Planner) ──────────────────────────────
        print("  Switching to Route Planner tab…")
        try:
            page.locator("button:has-text('Route Planner')").first.click()
            page.wait_for_timeout(1500)
            print("  ✅ Route Planner tab active")
        except Exception as exc:
            print(f"  WARNING: tab switch failed ({exc})")

        # ── Wait for hint buttons ─────────────────────────────────────────
        print("  Waiting for hint buttons…")
        try:
            page.wait_for_selector(f"button:has-text('{DEMO_BUTTON_TEXT}')", timeout=30_000)
        except Exception:
            print("  WARNING: hint buttons not found in time, continuing anyway")

        # ── Frame 3: Route Planner with hint buttons ──────────────────────
        snap(page, 3000)

        # ── Click the demo route ──────────────────────────────────────────
        print(f"  Clicking demo route button '{DEMO_BUTTON_TEXT}'…")
        btn = page.locator(f"button:has-text('{DEMO_BUTTON_TEXT}')").first
        try:
            btn.wait_for(state="visible", timeout=30_000)
            page.evaluate("window.scrollTo(0, 0)")
            btn.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            btn.click()
            print("  ✅ Button clicked")
        except Exception as exc:
            print(f"  WARNING: click failed ({exc}) — trying JS click")
            try:
                btn.evaluate("el => el.click()")
            except Exception as exc2:
                print(f"  WARNING: JS click also failed ({exc2})")
        page.wait_for_timeout(2000)

        # Confirm click registered: stepper should appear within 20 s
        print("  Waiting for stepper to confirm pipeline started…")
        try:
            page.wait_for_selector(".riq-stepper", timeout=20_000)
            print("  ✅ Stepper appeared — pipeline is running")
        except Exception:
            print("  NOTE: stepper not detected — pipeline may not have started")

        # ── Frame 3: pipeline kicked off (parse step likely active) ───────
        snap(page, 2500)

        # ── Poll until result renders, snapping on stepper state changes ──
        print("  Polling pipeline progress (up to 3 min)…")
        prev_stepper = ""
        prev_narrative = ""
        result_snapped = False

        for tick in range(100):  # up to 300 s at 3 s intervals
            page.wait_for_timeout(3000)

            # Result detection: iframe (Folium map / stop cards) OR narrative expander text
            result_done = (
                page.locator("iframe").count() > 0
                or page.locator("text=Route narrative").count() > 0
            )

            # Detect stepper change
            stepper_html = ""
            try:
                el = page.query_selector(".riq-stepper")
                if el:
                    stepper_html = el.inner_html()
            except Exception:
                pass

            # Detect narrative streaming text (span "Generating narrative…")
            narrative_html = ""
            try:
                spans = page.locator("span:has-text('Generating narrative')").all()
                if spans:
                    narrative_html = spans[0].text_content()[:80]
            except Exception:
                pass

            should_snap = (
                stepper_html != prev_stepper
                or (narrative_html and narrative_html != prev_narrative)
                or (tick % 5 == 0 and tick > 0)  # periodic fallback every ~15 s
            )

            if should_snap:
                snap(page, 2500)
                prev_stepper = stepper_html
                prev_narrative = narrative_html

            if result_done and not result_snapped:
                page.wait_for_timeout(2500)
                print("  ✅ Result rendered (map iframe detected) — capturing")
                snap(page, 4000)
                result_snapped = True
                break

        if not result_snapped:
            print("  ⚠ Pipeline did not finish within 3 min — capturing current state")
            snap(page, 3000)

        # ── Scroll to route summary + top of map ─────────────────────────
        page.evaluate("window.scrollTo({top: 400, behavior: 'instant'})")
        page.wait_for_timeout(2000)
        snap(page, 4000)

        # ── Scroll to show Folium map fully ──────────────────────────────
        page.evaluate("window.scrollTo({top: 700, behavior: 'instant'})")
        page.wait_for_timeout(2000)
        snap(page, 5000)

        # ── Scroll to stop cards ──────────────────────────────────────────
        page.evaluate("window.scrollTo({top: 1100, behavior: 'instant'})")
        page.wait_for_timeout(2000)
        snap(page, 5000)

        # ── Scroll to narrative expander ──────────────────────────────────
        page.evaluate("window.scrollTo({top: 1700, behavior: 'instant'})")
        page.wait_for_timeout(2500)
        snap(page, 6000)

        browser.close()

    _make_gif(screenshots)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"▶  Starting Streamlit on port {PORT}…")
    env = {**os.environ, "STREAMLIT_SERVER_HEADLESS": "true"}
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.port", str(PORT),
            "--server.headless", "true",
            "--server.runOnSave", "false",
            "--logger.level", "error",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        print("⏳  Waiting for server to respond…")
        if not _wait_for_server(120):
            proc.terminate()
            sys.exit("  ERROR: Streamlit did not start within 120 s")
        print(f"  ✅  Server ready at {URL}")
        time.sleep(2)

        _record()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("  Streamlit process stopped")


if __name__ == "__main__":
    main()
