import os
import time
import logging
import threading
import gc
import sys
import traceback
import io
from datetime import datetime
from collections import deque
from flask import Flask, Response, request, redirect, url_for, send_file
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
TARGET_URL = 'https://drednot.io/'
ANONYMOUS_LOGIN_KEY = os.environ.get("ANONYMOUS_LOGIN_KEY", "_M85tFxFxIRDax_nh-HYm1gT")

# RESTART LIMITS (To prevent RAM leaks on Render)
MAX_CYCLES_PER_SESSION = 20  
MAX_MINUTES_PER_SESSION = 30

# --- GLOBAL STATE & LOCKS ---
driver_lock = threading.Lock() # Crucial for thread-safe screenshots
driver = None

BOT_STATE = {
    "status": "Initializing...",
    "start_time": datetime.now(),
    "cycles_completed": 0,
    "last_event": "None yet.",
    "event_log": deque(maxlen=15)
}

def log_event(message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    full_message = f"[{timestamp}] {message}"
    BOT_STATE["event_log"].appendleft(full_message)
    BOT_STATE["last_event"] = message
    logging.info(message)

# --- BROWSER SETUP (DOCKER OPTIMIZED) ---
def setup_driver():
    logging.info("🚀 Launching Headless Chromium (Docker Mode)")
    opts = Options()
    opts.binary_location = "/usr/bin/chromium"
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,720")
    
    # RAM Optimizations
    opts.add_argument("--js-flags=--max-old-space-size=128")
    opts.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})

    service = Service(executable_path="/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=opts)

# --- THE CORE BOT LOGIC ---
def start_bot_cycle():
    global driver
    new_driver = setup_driver()
    
    with driver_lock:
        driver = new_driver
    
    wait = WebDriverWait(driver, 30)
    cycles_in_this_session = 0
    start_time = time.time()

    try:
        log_event(f"📍 Loading {TARGET_URL}")
        with driver_lock:
            driver.get(TARGET_URL)
        time.sleep(15)

        while True:
            # Check for Session Expiry
            elapsed_mins = (time.time() - start_time) / 60
            if cycles_in_this_session >= MAX_CYCLES_PER_SESSION or elapsed_mins >= MAX_MINUTES_PER_SESSION:
                log_event("♻️ Session limit reached. Performing clean restart...")
                break

            gc.collect()

            with driver_lock:
                # --- 1. HANDLE "ACCEPT" NOTICE ---
                try:
                    accept_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept')]")
                    if accept_btns:
                        log_event("✅ Notice found. Clicking Accept...")
                        driver.execute_script("arguments[0].click();", accept_btns[0])
                        time.sleep(3)
                except: pass

                # --- 2. HANDLE LOGIN / RESTORE ---
                try:
                    if not driver.find_elements(By.XPATH, "//button[contains(.,'New Ship')]"):
                        log_event("🔑 Menu not found. Checking for Restore...")
                        
                        restore_links = driver.find_elements(By.XPATH, "//a[contains(text(),'Restore')]")
                        if restore_links:
                            driver.execute_script("arguments[0].click();", restore_links[0])
                            time.sleep(2)

                            key_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".modal-window input")))
                            key_input.send_keys(ANONYMOUS_LOGIN_KEY)
                            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", key_input)
                            time.sleep(1)

                            submit_btn = driver.find_element(By.XPATH, "//button[text()='Submit']")
                            driver.execute_script("arguments[0].click();", submit_btn)
                            log_event("🔑 Key submitted.")
                            time.sleep(4)

                        play_btns = driver.find_elements(By.XPATH, "//button[contains(text(),'Play Anonymously')]")
                        if play_btns:
                            driver.execute_script("arguments[0].click();", play_btns[0])
                            log_event("🔑 Clicking Play Anonymously...")
                            time.sleep(6)
                except Exception as e:
                    log_event(f"⚠️ Login phase error: {str(e)[:50]}")

                # --- 3. SHIP CREATION CYCLE ---
                try:
                    driver.implicitly_wait(5)
                    menu_btn = driver.find_elements(By.XPATH, "//button[contains(.,'New Ship')]")
                    
                    if menu_btn:
                        BOT_STATE["status"] = "Creating Ship..."
                        log_event("🚢 Creating New Ship...")
                        driver.execute_script("arguments[0].click();", menu_btn[0])
                        time.sleep(2)

                        launch_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Launch')]")))
                        driver.execute_script("arguments[0].click();", launch_btn)
                        
                        log_event("🚀 Ship Launched! Holding 15s...")
                        BOT_STATE["status"] = "In Game"
                        time.sleep(15)

                        log_event("🚪 Exiting Ship...")
                        driver.execute_script("""
                            const exit = document.querySelector('#exit_button') || 
                                         [...document.querySelectorAll('button')].find(b => b.textContent.includes('Exit'));
                            if (exit) exit.click();
                        """)
                        wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(.,'New Ship')]")))
                        
                        cycles_in_this_session += 1
                        BOT_STATE["cycles_completed"] += 1
                        log_event(f"✨ Cycle {BOT_STATE['cycles_completed']} Done.")
                    else:
                        log_event("⏳ Waiting for main menu...")
                except Exception as e:
                    log_event(f"❌ Cycle error: {str(e)[:50]}")
                    driver.refresh()
                    time.sleep(10)
            
            time.sleep(5) # Delay between state checks

    except Exception:
        log_event(f"🔥 Driver Crash: {traceback.format_exc()[:100]}")
    finally:
        log_event("🧹 Shutting down browser...")
        with driver_lock:
            if driver:
                driver.quit()
                driver = None

# --- FLASK DASHBOARD & SCREENSHOT ---
flask_app = Flask('')

@flask_app.route('/screenshot')
def get_screenshot():
    global driver
    # Try to acquire lock quickly to not block the main loop too long
    acquired = driver_lock.acquire(timeout=10)
    if not acquired:
        return "Could not acquire browser lock (Bot might be busy)", 503
    
    try:
        if driver is None:
            return "Browser not initialized", 404
        
        # Take screenshot as PNG bytes
        png = driver.get_screenshot_as_png()
        return send_file(io.BytesIO(png), mimetype='image/png')
    except Exception as e:
        return f"Failed to capture screenshot: {e}", 500
    finally:
        driver_lock.release()

@flask_app.route('/')
def health_check():
    html = f"""
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="10">
    <title>Drednot Cycle Bot</title><style>
        body {{ font-family: sans-serif; background: #121212; color: #eee; padding: 20px; }}
        .card {{ background: #1e1e1e; padding: 20px; border-radius: 8px; border: 1px solid #333; }}
        .stat {{ margin-bottom: 10px; font-size: 1.1em; }}
        .label {{ color: #4ec9b0; font-weight: bold; }}
        .log-box {{ background: #000; padding: 10px; border-radius: 4px; height: 300px; overflow-y: auto; font-family: monospace; font-size: 0.9em; border: 1px solid #444; }}
        .btn {{ display: inline-block; background: #4ec9b0; color: #121212; padding: 10px 20px; border-radius: 4px; text-decoration: none; font-weight: bold; margin-top: 15px; }}
        .btn:hover {{ background: #63d8c1; }}
    </style></head>
    <body><div class="card">
        <h1>Drednot Bot Dashboard</h1>
        <div class="stat"><span class="label">Status:</span> {BOT_STATE['status']}</div>
        <div class="stat"><span class="label">Total Cycles:</span> {BOT_STATE['cycles_completed']}</div>
        <div class="stat"><span class="label">Last Event:</span> {BOT_STATE['last_event']}</div>
        
        <a href="/screenshot" target="_blank" class="btn">📷 View Live Screenshot</a>
        
        <hr style="border: 0; border-top: 1px solid #333; margin: 20px 0;">
        <h3>Event Log</h3>
        <div class="log-box">{'<br>'.join(BOT_STATE['event_log'])}</div>
    </div></body></html>
    """
    return Response(html, mimetype='text/html')

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()

    while True:
        try:
            BOT_STATE["status"] = "Starting session..."
            start_bot_cycle()
            time.sleep(10)
        except Exception as e:
            log_event(f"SYSTEM: Restarting in 30s... Error: {e}")
            time.sleep(30)
