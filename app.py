import asyncio
import os
from playwright.async_api import async_playwright, Playwright, Route
from fastapi import FastAPI, HTTPException, Query
import uvicorn

# -------------------------------------------------------------------
# Playwright ബ്രൗസർ ആപ്ലിക്കേഷൻ തുടങ്ങുമ്പോൾ ഒരു തവണ മാത്രം ലോഞ്ച് ചെയ്യുന്നു.
# ഇത് ഓരോ തവണയും പുതിയ ബ്രൗസർ തുടങ്ങി മെമ്മറി പാഴാക്കുന്നത് ഒഴിവാക്കുന്നു.
# -------------------------------------------------------------------
playwright_instance: Playwright = None
browser = None

app = FastAPI(
    title="Powerful Scraper API",
    description="A scraping API using Playwright and FastAPI"
)

@app.on_event("startup")
async def startup_event():
    """ആപ്ലിക്കേഷൻ സ്റ്റാർട്ട് ചെയ്യുമ്പോൾ Playwright-ഉം ബ്രൗസറും ലോഞ്ച് ചെയ്യുന്നു."""
    global playwright_instance, browser
    playwright_instance = await async_playwright().start()
    # മെമ്മറി കുറവ് ഉപയോഗിക്കുന്ന Firefox ഉപയോഗിക്കുന്നു
    browser = await playwright_instance.firefox.launch()
    print("✅ Playwright browser has been launched successfully.")

@app.on_event("shutdown")
async def shutdown_event():
    """ആപ്ലിക്കേഷൻ നിർത്തുമ്പോൾ ബ്രൗസർ ക്ലോസ് ചെയ്യുന്നു."""
    if browser:
        await browser.close()
    if playwright_instance:
        await playwright_instance.stop()
    print("🔥 Playwright browser has been shut down.")

# -------------------------------------------------------------------
# മെമ്മറി ലാഭിക്കാൻ ചിത്രങ്ങളും, സ്റ്റൈലുകളും, ഫോണ്ടുകളും ബ്ലോക്ക് ചെയ്യുന്നു.
# -------------------------------------------------------------------
async def block_unnecessary_requests(route: Route):
    """Avoid loading images, styles, and fonts to save memory and speed up."""
    if route.request.resource_type in ["image", "stylesheet", "font", "media", "script"]:
        # Allow scripts from the main domain, block third-party scripts
        if "script" == route.request.resource_type and route.request.url.startswith(route.request.frame.url.split('/')[0:3][2]):
             await route.continue_()
        else:
            await route.abort()
    else:
        await route.continue_()
        
# -------------------------------------------------------------------
# പ്രധാനപ്പെട്ട API എൻഡ്‌പോയിന്റ്
# -------------------------------------------------------------------
@app.get("/scrape")
async def scrape_video_details(url: str = Query(..., description="The URL of the video page to scrape")):
    """
    ഒരു URL-ൽ നിന്ന് വീഡിയോയുടെ പേരും (title), ക്വാളിറ്റി ലിങ്കുകളും (qualities)
    Playwright ഉപയോഗിച്ച് സ്ക്രാപ്പ് ചെയ്തെടുക്കുന്നു.
    """
    if not browser:
        raise HTTPException(status_code=503, detail="Browser is not initialized.")
    
    context = await browser.new_context()
    page = await context.new_page()

    captured_links = set()

    # നെറ്റ്‌വർക്ക് അഭ്യർത്ഥനകൾ പിടിച്ചെടുക്കാൻ ഒരു ഇവന്റ് ഹാൻഡ്‌ലർ സെറ്റ് ചെയ്യുന്നു
    def handle_request(request):
        if any(ext in request.url for ext in [".m3u8", ".mp4"]):
            if "m3u8" in request.url or "mp4" in request.url:
                captured_links.add(request.url)
    
    page.on("request", handle_request)

    try:
        # അനാവശ്യ അഭ്യർത്ഥനകൾ ബ്ലോക്ക് ചെയ്യുന്നു
        await page.route("**/*", block_unnecessary_requests)
        
        # പേജിലേക്ക് പോകുന്നു (60 സെക്കൻഡ് വരെ കാത്തിരിക്കും)
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")

        # JavaScript ലോഡ് ആകാനും നെറ്റ്‌വർക്ക് കോളുകൾ വരാനും 10 സെക്കൻഡ് കാത്തിരിക്കുന്നു
        await page.wait_for_timeout(10000)
        
        # പേജിന്റെ തലക്കെട്ട് (Title) എടുക്കുന്നു
        title = await page.title()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    finally:
        # പേജും കോൺടെക്സ്റ്റും ക്ലോസ് ചെയ്ത് മെമ്മറി ഫ്രീയാക്കുന്നു
        await page.close()
        await context.close()

    if not captured_links and not title:
        raise HTTPException(status_code=404, detail="Could not find a title or any video links.")

    return {
        "title": title,
        "qualities": list(captured_links)
    }

# -------------------------------------------------------------------
# ഈ കോഡ് നേരിട്ട് റൺ ചെയ്യുമ്പോൾ Uvicorn സെർവർ തുടങ്ങാൻ
# -------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
