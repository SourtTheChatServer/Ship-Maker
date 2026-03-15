import os
import time
import logging
import threading
import gc
import sys
import traceback
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIG ---
TARGET_URL = 'https://drednot.io/'
ANONYMOUS_LOGIN_KEY = '_M85tFxFxIRDax_nh-HYm1gT'

# RESTART SETTINGS
MAX_CYCLES_PER_SESSION = 20  # Restart browser after 20 ship launches
MAX_MINUTES_PER_SESSION = 30 # Restart browser every 30 minutes regardless of cycles

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# --- WASM HOOK ---
WASM_HOOK_SCRIPT = """
(function() {
    'use strict';
    if (window.__wasmHookInstalled) return;
    window.__wasmHookInstalled = true;
    const win = window;
    const origInst = win.WebAssembly.instantiate;
    const origStream = win.WebAssembly.instantiateStreaming;
    const forceTrue = () => 1;
    function patch(imports) {
        try {
            if (!imports || !imports.wbg) return;
            for (const k in imports.wbg) {
                if (k.indexOf('isTrusted') !== -1) imports.wbg[k] = forceTrue;
            }
        } catch (e) {}
    }
    win.WebAssembly.instantiate = function(buf, imports) { patch(imports); return origInst.apply(this, arguments); };
    win.WebAssembly.instantiateStreaming = function(src, imports) { patch(imports); return origStream.apply(this, arguments); };
})();
"""

def setup_driver():
    logging.info("🚀 Launching Fresh Chromium Instance")
    opts = Options()
    opts.binary_location = "/usr/bin/chromium" 
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage") 
    opts.add_argument("--window-size=1366,768")   
    opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    opts.add_argument("--renderer-process-limit=1")
    opts.add_argument("--js-flags=--max-old-space-size=128 --expose-gc")

    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)
    opts.page_load_strategy = 'eager' 

    driver = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": WASM_HOOK_SCRIPT})
    return driver

def start_bot():
    driver = setup_driver()
    wait = WebDriverWait(driver, 45) 
    
    # TRACKERS FOR RESTART
    cycles_completed = 0
    start_time = time.time()

    try:
        logging.info(f"📍 Loading {TARGET_URL}")
        driver.get(TARGET_URL)
        time.sleep(10) 

        while True:
            # CHECK IF WE NEED A FULL RESTART
            elapsed_minutes = (time.time() - start_time) / 60
            if cycles_completed >= MAX_CYCLES_PER_SESSION:
                logging.info(f"♻️ Limit reached ({MAX_CYCLES_PER_SESSION} cycles). Performing full restart...")
                break
            if elapsed_minutes >= MAX_MINUTES_PER_SESSION:
                logging.info(f"♻️ Time limit reached ({int(elapsed_minutes)} mins). Performing full restart...")
                break

            gc.collect() 

            # --- STEP 1: LOGIN ---
            try:
                driver.implicitly_wait(5)
                if not driver.find_elements(By.XPATH, "//button[contains(.,'New Ship')]"):
                    logging.info("🔑 Logging in...")
                    restore = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(),'Restore')]")))
                    driver.execute_script("arguments[0].click();", restore)
                    
                    key_input = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.modal-window input")))
                    key_input.send_keys(ANONYMOUS_LOGIN_KEY)
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input',{bubbles:true}));", key_input)
                    
                    submit = driver.find_element(By.XPATH, "//button[text()='Submit']")
                    driver.execute_script("arguments[0].click();", submit)
                    time.sleep(3)
                    
                    play = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Play Anonymously')]")))
                    driver.execute_script("arguments[0].click();", play)
                    time.sleep(5)
            except Exception:
                driver.refresh()
                time.sleep(10)
                continue

            # --- STEP 2: GAME CYCLE ---
            try:
                btn_new = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'New Ship')]")))
                driver.execute_script("arguments[0].click();", btn_new)
                time.sleep(2)

                btn_launch = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Launch')]")))
                driver.execute_script("arguments[0].click();", btn_launch)
                
                time.sleep(8) # Stay in game

                # Exit
                driver.execute_script("""
                    const exitBtn = document.querySelector('#exit_button') || 
                                    [...document.querySelectorAll('button')].find(b => b.textContent.includes('Exit'));
                    if (exitBtn) exitBtn.click();
                """)
                
                wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(.,'New Ship')]")))
                
                cycles_completed += 1
                logging.info(f"✅ Cycle {cycles_completed} Done. (Session: {int(elapsed_minutes)}m elapsed)")
                time.sleep(2)

            except Exception as e:
                logging.warning("⚠️ Cycle error, refreshing page...")
                driver.refresh()
                time.sleep(10)

    except Exception:
        logging.error(f"🔥 Critical Error: {traceback.format_exc()}")
    finally:
        logging.info("🧹 Closing browser for cleanup...")
        driver.quit() # This ensures the process is killed

# --- FLASK ---
app = Flask(__name__)
@app.route("/")
def health(): return "Bot Active"

def main():
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000, use_reloader=False), daemon=True).start()
    
    while True:
        try:
            start_bot() # This runs until it hits the cycle/time limit or crashes
            logging.info("💤 Cooling down for 10s before fresh start...")
            time.sleep(10)
        except Exception:
            time.sleep(30)

if __name__ == "__main__":
    main()
