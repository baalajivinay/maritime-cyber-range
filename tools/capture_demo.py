import asyncio
import os
import time
from playwright.async_api import async_playwright

async def run_demo():
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "evidence", "demo_captures")
    os.makedirs(output_dir, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Capture video? We can use record_video_dir
        context = await browser.new_context(
            record_video_dir=output_dir,
            record_video_size={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        print("Navigating to dashboard...")
        await page.goto("http://localhost:8080")
        await page.wait_for_selector("#map")
        
        # Give it a few seconds to load the map and initial data
        await page.wait_for_timeout(5000)
        
        print("Taking baseline screenshot...")
        await page.screenshot(path=os.path.join(output_dir, "01_baseline.png"))
        
        print("Ready for next step. Will wait for instructions.")
        
        # We can implement a simple signaling mechanism (e.g. file-based)
        # to trigger screenshots at exact moments.
        steps = [
            "02_gps_spoof_step.png",
            "03_gps_spoof_off.png",
            "04_ais_ghost.png",
            "05_ais_impersonate.png",
            "06_all_clear.png"
        ]
        
        for step in steps:
            # Wait for a trigger file to exist
            trigger_file = os.path.join(output_dir, "trigger_" + step)
            print(f"Waiting for {trigger_file}...")
            while not os.path.exists(trigger_file):
                await page.wait_for_timeout(500)
            print(f"Taking screenshot: {step}")
            await page.screenshot(path=os.path.join(output_dir, step))
            os.remove(trigger_file)
            
        print("Closing browser...")
        video = page.video  # must grab the handle before closing
        await context.close()
        await browser.close()

        # Ask Playwright for THIS page's exact recorded file, rather than
        # globbing output_dir for "the first .webm" -- a stray file from a
        # prior/failed run there would otherwise get renamed instead.
        if video is not None:
            recorded_path = await video.path()
            os.rename(recorded_path, os.path.join(output_dir, "demo_sequence.webm"))
        print("Done.")

if __name__ == "__main__":
    asyncio.run(run_demo())
