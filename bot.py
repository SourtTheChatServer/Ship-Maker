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
# Set this in Render's Environment Variables as BOT_KEY
ANONYMOUS_LOGIN_KEY = os.getenv('BOT_KEY', '_M85tFxFxIRDax_nh-HYm1gT')

# RESTART LIMITS (Important for Render's 512MB RAM)
MAX_CYCLES_PER_SESSION = 15  
MAX_MINUTES_PER_SESSION = 25

# --- GLOBAL STATE & LOCKS ---
driver_lock = threading.Lock()
driver = None

BOT_STATE = {
    "status": "Initializing...",
    "start_time": datetime.now(),
    "cycles_completed": 0,
    "last_event": "None yet.",
    "event_log": deque(maxlen=15)
}

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')

def log_event(message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    full_message = f"[{timestamp}] {message}"
    BOT_STATE["event_log"].appendleft(full_message)
    BOT_STATE["last_event"] = message
    logging.info(message)

# --- BROWSER SETUP (FIXES WEBGL ERROR) ---
def setup_driver():
    log_event("🚀 Launching Headless Chromium with Software WebGL...")
    opts = Options()
    opts.binary_location = "/usr/bin/chromium"
    
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,720")

    # --- THE WEBGL FIXES ---
    opts.add_argument("--enable-webgl")
    opts.add_argument("--use-gl=angle")
    opts.add_argument("--use-angle=swiftshader") # Force CPU to handle graphics
    opts.add_argument("--mute-audio")
    # ----------------------

    # RAM Management
    opts.add_argument("--js-flags=--max-old-space-size=128")
    opts.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2
    })

    service = Service(executable_path="/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=opts)

# --- THE BOT LOGIC ---
def start_bot_cycle():
    global driver
    new_driver = setup_driver()
    
    with driver_lock:
        driver = new_driver
    
    wait = WebDriverWait(driver, 30)
    cycles_in_session = 0
    session_start = time.time()

    try:
        log_event(f"📍 Loading {TARGET_URL}")
        with driver_lock:
            driver.get(TARGET_URL)
        
        time.sleep(15) # Wait for engine to boot

        while True:
            # Check Session Limits
            elapsed = (time.time() - session_start) / 60
            if cycles_in_session >= MAX_CYCLES_PER_SESSION or elapsed >= MAX_MINUTES_PER_SESSION:
                log_event("♻️ Session limit reached. Refreshing browser process...")
                break

            gc.collect()

            with driver_lock:
                # 1. HANDLE "ACCEPT" NOTICE
                try:
                    accept = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept')]")
                    if accept:
                        log_event("✅ Clicking Accept on Notice modal...")
                        driver.execute_script("arguments[0].click();", accept[0])
                        time.sleep(3)
                except: pass

                # 2. HANDLE LOGIN / RESTORE
                try:
                    # Check if 'New Ship' (menu) is missing
                    if not driver.find_elements(By.XPATH, "//button[contains(.,'New Ship')]"):
                        log_event("🔑 Checking for Restore...")
                        
                        restore = driver.find_elements(By.XPATH, "//a[contains(text(),'Restore')]")
                        if restore:
                            driver.execute_script("arguments[0].click();", restore[0])
                            time.sleep(2)

                            key_in = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".modal-window input")))
                            key_in.send_keys(ANONYMOUS_LOGIN_KEY)
                            # Trigger input event so Submit button enables
                            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", key_in)
                            time.sleep(1)

                            submit = driver.find_element(By.XPATH, "//button[text()='Submit']")
                            driver.execute_script("arguments[0].click();", submit)
                            log_event("🔑 Key submitted.")
                            time.sleep(4)

                        play = driver.find_elements(By.XPATH, "//button[contains(text(),'Play Anonymously')]")
                        if play:
                            driver.execute_script("arguments[0].click();", play[0])
                            log_event("🔑 Clicking Play Anonymously...")
                            time.sleep(6)
                except Exception as e:
                    log_event(f"⚠️ Login Error: {str(e)[:40]}")

                # 3. GAME CYCLE
                try:
                    driver.implicitly_wait(2)
                    menu_btn = driver.find_elements(By.XPATH, "//button[contains(.,'New Ship')]")
                    
                    if menu_btn:
                        BOT_STATE["status"] = "Creating Ship..."
                        log_event("🚢 Clicking New Ship...")
                        driver.execute_script("arguments[0].click();", menu_btn[0])
                        time.sleep(2)

                        launch = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Launch')]")))
                        driver.execute_script("arguments[0].click();", launch)
                        
                        log_event("🚀 Launched! Holding 15s...")
                        BOT_STATE["status"] = "In Game"
                        time.sleep(15)

                        log_event("🚪 Exiting...")
                        driver.execute_script("""
                            const btn = document.querySelector('#exit_button') || 
                                        [...document.querySelectorAll('button')].find(b => b.textContent.includes('Exit'));
                            if (btn) btn.click();
                        """)
                        time.sleep(5)
                        
                        cycles_in_session += 1
                        BOT_STATE["cycles_completed"] += 1
                        log_event(f"✨ Cycle {BOT_STATE['cycles_completed']} Done.")
                    else:
                        log_event("⏳ Waiting for menu...")
                except Exception as e:
                    log_event(f"❌ Cycle Fail: {str(e)[:40]}")
                    driver.refresh()
                    time.sleep(10)
            
            time.sleep(5)

    except Exception:
        log_event(f"🔥 Crash: {traceback.format_exc()[:100]}")
    finally:
        with driver_lock:
            if driver:
                driver.quit()
                driver = None

# --- FLASK SERVER ---
flask_app = Flask('')

@flask_app.route('/screenshot')
def get_screenshot():
    global driver
    acquired = driver_lock.acquire(timeout=5)
    if not acquired: return "Browser Busy", 503
    try:
        if not driver: return "No Browser", 404
        return send_file(io.BytesIO(driver.get_screenshot_as_png()), mimetype='image/png')
    finally: driver_lock.release()

@flask_app.route('/')
def health():
    html = f"""
    <!DOCTYPE html><html><head><meta http-equiv="refresh" content="10"><style>
    body{{background:#121212;color:#eee;font-family:sans-serif;padding:20px;}}
    .log{{background:#000;padding:10px;height:250px;overflow:auto;font-family:monospace;border:1px solid #444;}}
    .btn{{background:#4ec9b0;color:#000;padding:10px;text-decoration:none;font-weight:bold;border-radius:4px;}}
    </style></head><body>
    <h1>Drednot Bot Control</h1>
    <p>Status: <b>{BOT_STATE['status']}</b> | Total Cycles: <b>{BOT_STATE['cycles_completed']}</b></p>
    <a href="/screenshot" target="_blank" class="btn">📷 View Current Screen</a>
    <h3>Event Log</h3><div class="log">{'<br>'.join(BOT_STATE['event_log'])}</div>
    </body></html>
    """
    return Response(html, mimetype='text/html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: flask_app.run(host='0.0.0.0', port=port), daemon=True).start()
    while True:
        BOT_STATE["status"] = "Starting Session..."
        start_bot_cycle()
        time.sleep(10)
