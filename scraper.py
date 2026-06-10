import os
# Force Playwright to use the global browser directory instead of the PyInstaller temp folder
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.expandvars(r"%USERPROFILE%\AppData\Local\ms-playwright")

import time
import asyncio
from datetime import datetime, timedelta
from playwright.async_api import async_playwright


async def run_scraper(email, password, start_date_str, end_date_str, download_dir, progress_callback=None, headless=False):
    """
    Automates logging into Sawyer and downloading rosters for all camps 
    in a date range.
    """
    if progress_callback:
        progress_callback("Starting browser...")
        
    async with async_playwright() as p:
        # Use a persistent browser context to remember login sessions, cookies, and 2FA status
        user_data_dir = os.path.expandvars(r"%USERPROFILE%\AppData\Local\SawyerRosterAutomation\edge_browser_profile")
        os.makedirs(user_data_dir, exist_ok=True)
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless, 
            channel="msedge",
            ignore_default_args=["--no-sandbox", "--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
            accept_downloads=True
        )

        # Mask automation signatures
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = context.pages[0] if context.pages else await context.new_page()
        
        # 1. Go to business portal (will redirect to sign-in page with correct return path)
        if progress_callback:
            progress_callback("Navigating to Sawyer portal...")
        await page.goto("https://www.hisawyer.com/portal")
        
        # 2. Check if we are already logged in (look for portal elements vs email input)
        if progress_callback:
            progress_callback("Checking login status...")
            
        is_logged_in = False
        try:
            # Race condition: wait for either email login input OR a portal element
            element = await page.wait_for_selector("input[type='email'], a[href*='/portal/'], .daily-calendar, [class*='calendar']", timeout=15000)
            tag_name = await element.evaluate("node => node.tagName.toLowerCase()")
            if tag_name != "input":
                is_logged_in = True
        except Exception:
            pass
            
        if not is_logged_in:
            if headless:
                raise Exception("Sawyer session expired or invalid. Please open the Sawyer Roster app and click 'Log in / Refresh Session'.")
                
            if progress_callback:
                progress_callback("Not logged in. Waiting for login page... Please complete any human verification/Cloudflare in the browser.")
            await page.wait_for_selector("input[type='email']", timeout=300000)
            
            # Fill credentials
            await page.fill("input[type='email']", email)
            await page.fill("input[type='password']", password)
            
            if progress_callback:
                progress_callback("Logging in... Please complete 2FA (and check 'Remember this computer') and CAPTCHAs if prompted.")
                
            # Click the visible login button
            await page.click("input[type='submit']:visible")
            
            # Wait for portal/calendar to load (give extra time for 2FA verification)
            try:
                await page.wait_for_url("**/portal/**", timeout=120000)
            except Exception:
                if progress_callback:
                    progress_callback("Login timeout. If you are completing 2FA, please finish it in the browser.")
                # Give user a chance to log in manually if they are doing 2FA
                await page.wait_for_selector("a[href*='/portal/'], .daily-calendar", timeout=120000)
        else:
            if progress_callback:
                progress_callback("Already logged in via saved browser session!")
            
        if progress_callback:
            progress_callback("Portal accessed successfully!")
            
        # Parse date range
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
        current_date = start_date
        
        os.makedirs(download_dir, exist_ok=True)
        
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            if progress_callback:
                progress_callback(f"Processing date: {date_str}")
                
            # Navigate to the daily calendar
            await page.goto(f"https://www.hisawyer.com/portal/daily_calendar?date={date_str}")
            
            # Wait for calendar container to load
            await page.wait_for_selector(".daily-calendar, [class*='calendar']", timeout=20000)
            
            # Extract all roster URLs on the daily calendar page using absolute links
            roster_urls = await page.evaluate("""() => {
                const urls = [];
                const links = document.querySelectorAll("a[href*='/portal/v2/rosters/']");
                links.forEach(link => {
                    const href = link.href;
                    if (href && !urls.includes(href)) {
                        urls.push(href);
                    }
                });
                return urls;
            }""")
            
            num_camps = len(roster_urls)
            if progress_callback:
                progress_callback(f"Found {num_camps} camps on {date_str}")
                
            for run_index, roster_url in enumerate(roster_urls):
                clean_camp = "Unknown_Camp"
                try:
                    if progress_callback:
                        progress_callback(f"Opening camp {run_index + 1}/{num_camps}...")
                        
                    # Navigate directly to the roster URL
                    await page.goto(roster_url)
                    await page.wait_for_url("**/portal/v2/rosters/**", timeout=30000)
                    
                    # Extract and clean camp name from the page header
                    try:
                        raw_camp_name = await page.evaluate("""() => {
                            const h1 = document.querySelector('h1');
                            if (h1 && h1.innerText) return h1.innerText.trim();
                            const title = document.querySelector('.roster-title, [class*="title"], [class*="header"] h1');
                            if (title && title.innerText) return title.innerText.trim();
                            return 'Unknown Camp';
                        }""")
                        
                        # Exclude Canteen Funds immediately
                        if raw_camp_name and "canteen" in raw_camp_name.lower() and "funds" in raw_camp_name.lower():
                            if progress_callback:
                                progress_callback(f"Skipping download for {raw_camp_name} (Excluded category)")
                            continue
                            
                        import re
                        clean_camp = re.sub(r'[^a-zA-Z0-9\s\-_]', '', raw_camp_name)
                        clean_camp = re.sub(r'[\s_]+', '_', clean_camp).strip('_')
                    except Exception:
                        pass
                    
                    # 1. Click "Roster Actions" dropdown button
                    roster_actions = page.locator("text=/Roster Actions/i").first
                    await roster_actions.wait_for(state="visible", timeout=20000)
                    
                    print_roster_btn = page.locator("text=/Print Roster/i").first
                    dropdown_opened = False
                    
                    for attempt in range(3):
                        try:
                            # Try standard click
                            await roster_actions.click(timeout=3000)
                            await page.wait_for_timeout(1000)
                            if await print_roster_btn.is_visible():
                                dropdown_opened = True
                                break
                        except Exception:
                            pass
                            
                        try:
                            # Try JS click
                            await roster_actions.evaluate("node => node.click()")
                            await page.wait_for_timeout(1000)
                            if await print_roster_btn.is_visible():
                                dropdown_opened = True
                                break
                        except Exception:
                            pass
                            
                    if not dropdown_opened:
                        # Check if Print Roster even exists on the page
                        if await print_roster_btn.count() == 0:
                            if progress_callback:
                                progress_callback(f"Camp {run_index + 1} has no Print Roster option (likely empty) - skipping.")
                            continue
                        else:
                            raise Exception("Timed out waiting for 'Print Roster' option to become visible.")
                            
                    # 2. Click "Print Roster"
                    await print_roster_btn.click()
                    
                    # 3. Wait for the "Print Roster" modal to appear and select "CSV Download only"
                    # First, wait for the modal text 'Select Format' to be visible on the page
                    await page.wait_for_selector("text=/Select Format/i", timeout=15000)
                    
                    # Locate the CSV option globally or scoped using multiple fallback selectors
                    csv_option = None
                    for selector in [
                        "text=/Download only/i",
                        "div:has-text('CSV') >> text=/Download only/i",
                        "div[role='dialog'] >> text=/Download only/i",
                        ".modal >> text=/Download only/i",
                        "text=/CSV/i"
                    ]:
                        try:
                            loc = page.locator(selector)
                            if await loc.count() > 0:
                                count = await loc.count()
                                for i in range(count):
                                    candidate = loc.nth(i)
                                    if await candidate.is_visible() or count == 1:
                                        csv_option = candidate
                                        break
                            if csv_option:
                                break
                        except Exception:
                            pass
                            
                    if not csv_option:
                        raise Exception("Could not locate the 'CSV (Download only)' option on the page.")
                        
                    # Click the CSV option card using multiple click strategies (standard click, JS click, parent click, closest container click)
                    clicked_csv = False
                    
                    # Define list of click methods to try sequentially
                    async def try_clicks():
                        nonlocal clicked_csv
                        # 1. Standard click
                        try:
                            await csv_option.click(timeout=3000)
                            clicked_csv = True
                            return
                        except Exception:
                            pass
                        
                        # 2. JS click on element
                        try:
                            await csv_option.evaluate("node => node.click()")
                            clicked_csv = True
                            return
                        except Exception:
                            pass
                            
                        # 3. JS click on closest div/button card container
                        try:
                            success = await csv_option.evaluate("""node => {
                                const card = node.closest('div, button, [role="button"]');
                                if (card) { card.click(); return true; }
                                return false;
                            }""")
                            if success:
                                clicked_csv = True
                                return
                        except Exception:
                            pass
                            
                        # 4. JS click on parent
                        try:
                            await csv_option.evaluate("node => node.parentElement.click()")
                            clicked_csv = True
                            return
                        except Exception:
                            pass
                            
                    await try_clicks()
                    if not clicked_csv:
                        raise Exception("Failed to select/click the CSV option card.")
                        
                    await page.wait_for_timeout(1500) # Wait for state change/selection style to update
                    
                    # 4. Locate the red "Generate" button inside the modal
                    generate_btn = None
                    for selector in [
                        "button:has-text('Generate')",
                        "[type='submit']:has-text('Generate')",
                        "text=/Generate/i",
                        "div[role='dialog'] >> text=/Generate/i",
                        ".modal >> text=/Generate/i"
                    ]:
                        try:
                            loc = page.locator(selector)
                            if await loc.count() > 0:
                                count = await loc.count()
                                for i in range(count):
                                    candidate = loc.nth(i)
                                    if await candidate.is_visible() or count == 1:
                                        generate_btn = candidate
                                        break
                            if generate_btn:
                                break
                        except Exception:
                            pass
                            
                    if not generate_btn:
                        raise Exception("Could not locate the 'Generate' button on the page.")
                        
                    if progress_callback:
                        progress_callback(f"Downloading roster {run_index + 1}/{num_camps}...")
                        
                    # Set up download listener and click Generate using multiple fallback click strategies
                    async with page.expect_download() as download_info:
                        clicked_gen = False
                        
                        # Try standard click
                        try:
                            await generate_btn.click(timeout=3000)
                            clicked_gen = True
                        except Exception:
                            pass
                            
                        if not clicked_gen:
                            # Try JS click
                            try:
                                await generate_btn.evaluate("node => node.click()")
                                clicked_gen = True
                            except Exception:
                                pass
                                
                        if not clicked_gen:
                            # Try parent JS click
                            try:
                                await generate_btn.evaluate("node => node.parentElement.click()")
                                clicked_gen = True
                            except Exception:
                                pass
                                
                        if not clicked_gen:
                            raise Exception("Failed to click the Generate button.")
                        
                    download = await download_info.value
                    
                    # Prepend the date and camp name to the suggested filename to preserve context
                    filename = f"{date_str}_{clean_camp}_{download.suggested_filename}"
                    if not filename.endswith(".csv"):
                        filename += ".csv"
                        
                    save_path = os.path.join(download_dir, filename)
                    await download.save_as(save_path)
                    
                    if progress_callback:
                        progress_callback(f"Saved: {filename}")
                        
                except Exception as e:
                    if progress_callback:
                        progress_callback(f"Error downloading camp {run_index + 1}: {e}")
                finally:
                    pass
                    
            current_date += timedelta(days=1)
        await context.close()
        if progress_callback:
            progress_callback("Scraping completed!")

# For testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        email = sys.argv[1]
        password = sys.argv[2]
        asyncio.run(run_scraper(
            email, password, 
            "2026-06-01", "2026-06-01", 
            r"C:\Users\thoma\.gemini\antigravity\scratch\sawyer_automation\downloads",
            print
        ))
