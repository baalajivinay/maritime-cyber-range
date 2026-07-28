import asyncio
from playwright.async_api import async_playwright

async def check_console():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"BROWSER ERROR: {err}"))
        
        await page.goto("http://localhost:8080")
        await page.wait_for_timeout(3000)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(check_console())
