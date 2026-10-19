from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


def main() -> int:
    installed = Path(os.environ["LOCALAPPDATA"]) / "ReverseWarp/extensions/chromium"
    if not (installed / "manifest.json").is_file():
        raise RuntimeError(f"installed extension is missing: {installed}")
    with tempfile.TemporaryDirectory(prefix="reversewarp-edge-selenium-") as temporary:
        temporary_path = Path(temporary)
        extension = temporary_path / "extension"
        profile = temporary_path / "profile"
        shutil.copytree(installed, extension)
        manifest_path = extension / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["content_scripts"] = [{
            "matches": ["http://127.0.0.1:18765/browser-video.html"],
            "js": ["content.js"],
            "run_at": "document_idle",
        }]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with (extension / "content.js").open("a", encoding="utf-8") as script:
            script.write(
                "\nsetTimeout(() => { const video = largestPlayingVideo(); "
                "if (video && !reverseWarpWindow.__reverseWarpController) { "
                "const controller = new ReverseWarpController(video); "
                "reverseWarpWindow.__reverseWarpController = controller; controller.start(); } }, 500);\n"
            )
        options = webdriver.EdgeOptions()
        options.add_argument(f"--disable-extensions-except={extension}")
        options.add_argument(f"--load-extension={extension}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--autoplay-policy=no-user-gesture-required")
        options.add_argument(f"--user-data-dir={profile}")
        driver = webdriver.Edge(options=options)
        try:
            driver.get("http://127.0.0.1:18765/browser-video.html")
            WebDriverWait(driver, 15).until(
                lambda active: active.find_element(By.TAG_NAME, "video").get_property("readyState") >= 2
            )
            label = WebDriverWait(driver, 90).until(
                lambda active: next(
                    (
                        element
                        for element in active.find_elements(By.TAG_NAME, "div")
                        if "Estimated reconstruction" in element.text
                        and ("corrected" in element.text or "bypass" in element.text)
                    ),
                    None,
                )
            )
            source_count = len(driver.find_elements(By.CSS_SELECTOR, "main > video"))
            overlay_count = len(driver.find_elements(By.CSS_SELECTOR, "html > video"))
            result = {
                "browser": driver.capabilities.get("browserName"),
                "browserVersion": driver.capabilities.get("browserVersion"),
                "label": label.text,
                "sourceVideoPreserved": source_count == 1,
                "processedVideoEmbedded": overlay_count == 1,
            }
            print(json.dumps(result, indent=2))
            if not all((result["sourceVideoPreserved"], result["processedVideoEmbedded"])):
                return 2
            label.click()
            WebDriverWait(driver, 10).until(
                lambda active: not active.find_elements(By.CSS_SELECTOR, "html > video")
            )
            print(json.dumps({"stopRevealedOriginal": True}))
            return 0
        finally:
            driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
