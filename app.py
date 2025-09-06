# -*- coding: utf-8 -*-

# ==============================================================================
# Ultimate Multi-Strategy Scraper API
# Author: Gemini (for a user's project)
# Date: 2025-09-06
# Description: This FastAPI application serves as a powerful web scraper.
# It uses a "manager" pattern to select the best scraping strategy 
# for a given website, optimizing for speed and memory usage.
# ==============================================================================

import os
import re
import json
import asyncio
import requests
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Query
import uvicorn
from playwright.async_api import async_playwright, Playwright

# --- Global Browser Instance for Playwright ---
# This is initialized as None and will only be launched when a complex 
# website requires a full browser, saving memory for most requests.
playwright_instance: Playwright = None
browser = None

# --- FastAPI Application Setup ---
app = FastAPI(
    title="Ultimate Scraper API",
    description="A professional scraper using the best strategy for each website.",
    version="1.0.0"
)

# --- Helper function to start Playwright ON-DEMAND ---
async def get_browser():
    """
    Checks if the Playwright browser is running. If not, it launches it.
    This ensures the memory-heavy browser is only active when absolutely necessary.
    """
    global playwright_instance, browser
    if browser is None or not browser.is_connected():
        print("🚀 INFO: Launching Playwright browser for a complex task...")
        playwright_instance = await async_playwright().start()
        # Using Firefox as it can sometimes be lighter on resources.
        browser = await playwright_instance.firefox.launch()
        print("✅ INFO: Playwright browser is now running.")
    return browser

# ==============================================================================
# SECTION 1: SCRAPING STRATEGIES
# Each function below is an "expert" for a specific website.
# ==============================================================================

# -------------------------------------------------------------------
# STRATEGY TYPE A: DIRECT HTML PARSING (FAST, LOW MEMORY)
# Use this for websites that hide video data inside the page's HTML source.
# -------------------------------------------------------------------

def scrape_xvideos_direct(page_url: str):
    """
    Scrapes XVideos by parsing the initial HTML content.
    The video data is stored in JavaScript variables within a <script> tag.
    This method is extremely fast and uses very little memory.
    """
    print(f"💡 INFO: Using DIRECT HTML strategy for {page_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    response = requests.get(page_url, headers=headers, timeout=15)
    response.raise_for_status()
    html_content = response.text
    
    title_match = re.search(r"html5player.setVideoTitle\('(.+?)'\);", html_content)
    title = title_match.group(1) if title_match else "Untitled Video"
    
    thumb_match = re.search(r"html5player.setVideoUrlPoster\('(.+?)'\);", html_content)
    thumbnail = thumb_match.group(1) if thumb_match else ""
    
    m3u8_match = re.search(r"html5player.setVideoHLS\('(.+?)'\);", html_content)
    m3u8_url = m3u8_match.group(1) if m3u8_match else ""
    
    qualities = {"HLS Playlist": m3u8_url} if m3u8_url else {}
    
    return {"title": title, "qualities": qualities, "thumbnail": thumbnail}

def scrape_xhamster_direct(page_url: str):
    """
    Scrapes XHamster by finding a JSON-LD script tag in the HTML.
    This JSON contains all the necessary metadata including the M3U8 playlist.
    This method is also very fast and efficient.
    """
    print(f"💡 INFO: Using DIRECT HTML strategy for {page_url}")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(page_url, headers=headers, timeout=15)
    response.raise_for_status()
    
    match = re.search(r'<script type="application/ld\+json">(.+?)</script>', response.text)
    if not match:
        raise ValueError("Could not find video JSON-LD data in the page.")
        
    data = json.loads(match.group(1))
    
    title = data.get('name', 'Untitled')
    thumbnail = data.get('thumbnailUrl', '')
    m3u8_url = data.get('contentUrl', '')
    qualities = {"HLS Playlist": m3u8_url} if m3u8_url else {}
    
    return {"title": title, "qualities": qualities, "thumbnail": thumbnail}

# -------------------------------------------------------------------
# STRATEGY TYPE B: ADVANCED PLAYWRIGHT (SLOWER, MEMORY INTENSIVE)
# Use this for complex websites that load video data only after
# JavaScript execution or user interaction (e.g., clicking a button).
# -------------------------------------------------------------------

async def advanced_playwright_scraper(page_url: str):
    """
    This is the most powerful (but slowest) strategy. It uses a real browser
    to visit the page, interacts with it, and intercepts network requests
    to find the video files. It's designed to find the largest video file.
    """
    print(f"🧠 INFO: Using ADVANCED PLAYWRIGHT strategy for {page_url}")
    b = await get_browser()
    context = await b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    page = await context.new_page()
    
    video_requests = []

    async def handle_response(response):
        content_type = response.headers.get("content-type", "").lower()
        is_video_url = any(ext in response.url for ext in [".mp4", ".m3u8", ".webm"])
        is_video_type = "video" in content_type or "mpegurl" in content_type or "binary/octet-stream" in content_type

        if is_video_url or is_video_type:
            try:
                size = int(response.headers.get("content-length", 0))
                if size > 100000: # Filter out small files/ads
                    video_requests.append({"url": response.url, "size": size})
                    print(f"✅ Intercepted video candidate: {response.url} (Size: {size / 1024:.2f} KB)")
            except (ValueError, TypeError):
                pass 

    page.on("response", handle_response)

    try:
        await page.goto(page_url, timeout=90000, wait_until="networkidle")
        title = await page.title()
        
        print("💡 INFO: Page loaded. Looking for a player or download button to click...")
        
        # Try to click common elements to trigger video loading
        click_selectors = [
            "button[data-test-id='download-button-main']", # For sites like Pixabay
            "div[id*='player']", 
            "div[class*='player']",
            "video"
        ]
        
        for selector in click_selectors:
            try:
                await page.click(selector, timeout=3000)
                print(f"✅ Clicked element: {selector}")
                break 
            except Exception:
                pass # If selector not found, just continue

        print("⏳ INFO: Waiting for 15 seconds for network activity to capture video links...")
        await page.wait_for_timeout(15000)

    finally:
        await page.close()
        await context.close()
        
    if not video_requests:
        return {"title": title, "qualities": {}}

    video_requests.sort(key=lambda x: x["size"], reverse=True)
    
    qualities = {}
    # Get the top 3 largest files to provide multiple qualities if available
    for i, video in enumerate(video_requests[:3]):
        label = f"Quality {i+1}"
        if ".m3u8" in video["url"]:
            label = "HLS Playlist"
        qualities[label] = video["url"]
    
    return {"title": title, "qualities": qualities}


# ==============================================================================
# SECTION 2: THE MANAGER
# This section decides which "expert" function to call for a given URL.
# ==============================================================================

# To add a new website, create a scraper function for it above,
# then add the website's domain and the function's name to this dictionary.
STRATEGY_MAP = {
    "mixkit.co": scrape_mixkit_direct,
    
    # XVideos-നെ ബ്ലോക്ക് ചെയ്യുന്നതുകൊണ്ട്, അതിന് Playwright ഉപയോഗിക്കാൻ പറയുന്നു
    "xvideos.com": advanced_playwright_scraper,
    
    "pixabay.com": advanced_playwright_scraper,
    "xhamster.com": scrape_xhamster_direct,
}


# ==============================================================================
# SECTION 3: THE API ENDPOINT
# This is the public URL your main bot will call.
# You should never need to change this part.
# ==============================================================================

@app.get("/scrape")
async def scrape_manager(url: str = Query(..., description="The URL of the video page to scrape")):
    """
    Receives a URL, identifies the domain, and calls the appropriate
    scraper function from the STRATEGY_MAP.
    """
    try:
        domain = urlparse(url).netloc.replace("www.", "")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL format.")

    if domain not in STRATEGY_MAP:
        raise HTTPException(status_code=404, detail=f"Website '{domain}' is not supported yet.")

    scraper_function = STRATEGY_MAP[domain]
    
    try:
        # Check if the function is async (needs await) or sync
        if asyncio.iscoroutinefunction(scraper_function):
            result = await scraper_function(url)
        else:
            result = scraper_function(url)
            
        if not result.get("qualities"):
             raise HTTPException(status_code=404, detail="Scraping finished, but no quality links were found.")

        print(f"✅ SUCCESS: Scraped '{result.get('title')}' using '{scraper_function.__name__}'")
        return result
    except Exception as e:
        print(f"❌ ERROR: Scraping failed for {domain}. Reason: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# SECTION 4: SERVER STARTUP
# ==============================================================================

if __name__ == "__main__":
    # This part is for running the app locally. Koyeb will use its own command.
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
