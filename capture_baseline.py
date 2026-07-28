import asyncio
import os
from playwright.async_api import async_playwright

async def run_demo():
    output_dir = os.path.expanduser("~/Maritime-sim/faculty_capture")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto("http://localhost:8080")
        await page.wait_for_selector("#map")
        
        await page.wait_for_timeout(3000)
        
        await page.screenshot(path=os.path.join(output_dir, "03_dashboard_baseline.png"))
        await page.screenshot(path=os.path.join(output_dir, "05_all_clear_final.png"))
        
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_demo())
