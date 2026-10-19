from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_Y = 0x59
KEY_UP = 0x0002


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--external-invoke", action="store_true")
    parser.add_argument("--keep-open-seconds", type=int, default=0)
    return parser.parse_args()


def edge_window_for_profile(profile: Path) -> int:
    escaped = str(profile).replace("'", "''")
    script = (
        "$candidate=Get-CimInstance Win32_Process | Where-Object {"
        f"$_.Name -eq 'msedge.exe' -and $_.CommandLine -like '*{escaped}*' -and $_.CommandLine -notlike '*--type=*'"
        "} | Select-Object -First 1;"
        "if($candidate){(Get-Process -Id $candidate.ProcessId).MainWindowHandle}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
    )
    handle = int(result.stdout.strip() or "0")
    if handle == 0:
        raise RuntimeError("dedicated Edge window was not found")
    return handle


def invoke_extension_action(window_handle: int) -> None:
    user32 = ctypes.windll.user32
    foreground = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
    target_thread = user32.GetWindowThreadProcessId(window_handle, None)
    current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(current_thread, foreground_thread, True)
    user32.AttachThreadInput(current_thread, target_thread, True)
    user32.ShowWindow(window_handle, 9)
    user32.BringWindowToTop(window_handle)
    focused = user32.SetForegroundWindow(window_handle)
    user32.AttachThreadInput(current_thread, target_thread, False)
    user32.AttachThreadInput(current_thread, foreground_thread, False)
    if not focused:
        raise RuntimeError("could not focus dedicated Edge window")
    time.sleep(0.5)
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_SHIFT, 0, 0, 0)
    user32.keybd_event(VK_Y, 0, 0, 0)
    user32.keybd_event(VK_Y, 0, KEY_UP, 0)
    user32.keybd_event(VK_SHIFT, 0, KEY_UP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEY_UP, 0)


def main() -> int:
    args = parse_args()
    extension = Path(os.environ["LOCALAPPDATA"]) / "ReverseWarp/extensions/chromium"
    with tempfile.TemporaryDirectory(prefix="reversewarp-edge-site-") as temporary:
        profile = Path(temporary) / "profile"
        options = webdriver.EdgeOptions()
        options.add_argument(f"--disable-extensions-except={extension}")
        options.add_argument(f"--load-extension={extension}")
        options.add_argument(f"--user-data-dir={profile}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--autoplay-policy=no-user-gesture-required")
        driver = webdriver.Edge(options=options)
        try:
            driver.get(args.url)
            try:
                WebDriverWait(driver, 45).until(
                    lambda active: active.execute_script(
                        "return [...document.querySelectorAll('video')].some(v=>v.readyState>=2&&v.getBoundingClientRect().width>80)||"
                        "[...document.querySelectorAll('iframe')].some(f=>f.getBoundingClientRect().width>240&&f.getBoundingClientRect().height>135)"
                    )
                )
            except TimeoutException:
                diagnostics = driver.execute_script(
                    "return {title:document.title,videos:document.querySelectorAll('video').length,"
                    "iframes:[...document.querySelectorAll('iframe')].map(frame=>({src:frame.src,title:frame.title,width:frame.clientWidth,height:frame.clientHeight}))};"
                )
                print(json.dumps({"site": args.name, "diagnostics": diagnostics}, indent=2))
                raise
            driver.execute_script(
                "const v=[...document.querySelectorAll('video')].sort((a,b)=>b.clientWidth*b.clientHeight-a.clientWidth*a.clientHeight)[0];"
                "if(v){v.muted=true;v.play().catch(()=>{});}"
            )
            if not args.external_invoke:
                invoke_extension_action(edge_window_for_profile(profile))
            label_text = WebDriverWait(driver, 120).until(
                lambda active: active.execute_script(
                    "const label=[...document.documentElement.children].find(element=>"
                    "element.tagName==='DIV'&&element.textContent.includes('Estimated reconstruction')&&"
                    "(element.textContent.includes('corrected')||element.textContent.includes('bypass')));"
                    "return label?.textContent||'';"
                )
            )
            result = {
                "site": args.name,
                "url": driver.current_url,
                "browser": driver.capabilities.get("browserName"),
                "browserVersion": driver.capabilities.get("browserVersion"),
                "label": label_text,
                "sourceVideoPresent": bool(driver.find_elements(By.TAG_NAME, "video")),
                "embeddedPlayerPresent": bool(driver.find_elements(By.TAG_NAME, "iframe")),
                "processedVideoEmbedded": len(driver.find_elements(By.CSS_SELECTOR, "html > video")) == 1,
            }
            print(json.dumps(result, indent=2), flush=True)
            if args.keep_open_seconds > 0:
                time.sleep(args.keep_open_seconds)
            driver.execute_script(
                "[...document.documentElement.children].find(element=>element.tagName==='DIV'&&"
                "element.textContent.includes('Estimated reconstruction'))?.click();"
            )
            WebDriverWait(driver, 10).until(
                lambda active: not active.find_elements(By.CSS_SELECTOR, "html > video")
            )
            result["stopRevealedOriginal"] = True
            print(json.dumps(result, indent=2), flush=True)
            return 0
        finally:
            driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
