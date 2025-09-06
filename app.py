import asyncio
import os
from playwright.async_api import async_playwright, Playwright, Route
from fastapi import FastAPI, HTTPException, Query
import uvicorn

# -------------------------------------------------------------------
# Playwright ബ്രൗസർ ആപ്ലിക്കേഷൻ തുടങ്ങുമ്പോൾ ഒരു തവണ മാത്രം ലോഞ്ച് ചെയ്യുന്നു
# -------------------------------------------------------------------
playwright_instance: Playwright = None
browser = None

app = FastAPI(
    title="Advanced Scraper API",
    description="An intelligent scraping API that interacts with pages."
)

@app.on_event("startup")
async def startup_event():
    global playwright_instance, browser
    playwright_instance = await async_playwright().start()
    browser = await playwright_instance.firefox.launch()
    print("✅ Advanced Playwright browser has been launched successfully.")

@app.on_event("shutdown")
async def shutdown_event():
    if browser: await browser.close()
    if playwright_instance: await playwright_instance.stop()
    print("🔥 Advanced Playwright browser has been shut down.")

# -------------------------------------------------------------------
# പ്രധാനപ്പെട്ട API എൻഡ്‌പോയിന്റ്
# -------------------------------------------------------------------
@app.get("/scrape")
async def scrape_video_details(url: str = Query(..., description="The URL of the video page to scrape")):
    if not browser:
        raise HTTPException(status_code=503, detail="Browser is not initialized.")
    
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    page = await context.new_page()

    captured_links = set()

    def handle_request(request):
        if any(ext in request.url for ext in [".m3u8", ".mp4", ".webm"]):
            captured_links.add(request.url)
    
    page.on("request", handle_request)

    try:
        await page.goto(url, timeout=60000, wait_until="networkidle")
        
        title = await page.title()

        # --- ഇതാണ് പുതിയ, ബുദ്ധിപരമായ ഭാഗം ---
        # "download" എന്ന വാക്കുള്ള ബട്ടണോ ലിങ്കോ കണ്ടെത്താൻ ശ്രമിക്കുന്നു
        download_button_selector = "button:has-text('Download'), a:has-text('Download')"
        
        try:
            # അങ്ങനെയൊരു ബട്ടൺ ഉണ്ടോ എന്ന് 5 സെക്കൻഡ് നോക്കുന്നു
            await page.wait_for_selector(download_button_selector, timeout=5000)
            
            # ബട്ടൺ ഉണ്ടെങ്കിൽ, അതിൽ ക്ലിക്ക് ചെയ്യുന്നു
            await page.click(download_button_selector)
            print(f"💡 Clicked a download button on {url}")
            
            # ക്ലിക്ക് ചെയ്ത ശേഷം ലിങ്കുകൾ വരാൻ 5 സെക്കൻഡ് കൂടി കാത്തിരിക്കുന്നു
            await page.wait_for_timeout(5000)

        except Exception:
            # ഡൗൺലോഡ് ബട്ടൺ കണ്ടെത്തിയില്ലെങ്കിൽ, പ്രശ്നമില്ല, മുന്നോട്ട് പോകുന്നു
            print(f"ℹ️ No specific download button found on {url}. Proceeding anyway.")
            await page.wait_for_timeout(10000) # സാധാരണപോലെ 10 സെക്കൻഡ് കാത്തിരിക്കുന്നു

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    finally:
        await page.close()
        await context.close()

    if not captured_links:
        # ഒരു ലിങ്കും കിട്ടിയില്ലെങ്കിൽ ഒരു എറർ നൽകുന്നു
        raise HTTPException(status_code=404, detail=f"Could not find any video links. The site might be protected or requires more interaction. Title found: '{title}'")

    return {
        "title": title,
        "qualities": list(captured_links)
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
