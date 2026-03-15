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
ANONYMOUS_LOGIN_KEY = os.getenv('BOT_KEY', '_M85tFxFxIRDax_nh-HYm1gT')

# RESTART SETTINGS
MAX_CYCLES_PER_SESSION = 15 
MAX_MINUTES_PER_SESSION = 25 

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)

WASM_HOOK_SCRIPT = """
(function() {
    'use strict';
    window.WebAssembly.instantiate = (orig => (buf, imp) => {
        if (imp && imp.wbg) {
            for (let k in imp.wbg) if (k.includes('isTrusted')) imp.wbg[k] = () => 1;
        }
        return orig(buf, imp);
    })(window.WebAssembly.instantiate);
})();
"""

def setup_driver():
    logging.info("🚀 Launching Fresh Chromium")
    opts = Options()
    opts.binary_location = "/usr/bin/chromium" 
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    # Small window size saves massive RAM
    opts.add_argument("--window-size=800,600")   
    opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Aggressive memory management for Render's 512MB limit
    opts.add_argument("--js-flags=--max-old-space-size=128")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-notifications")

    prefs = {
        "profile.managed_default_content_settings.images": 2, 
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.media_stream": 2
    }
    opts.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": WASM_HOOK_SCRIPT})
    return driver

def start_bot():
    driver = setup_driver()
    wait = WebDriverWait(driver, 30) # Reduced wait to catch hangs faster
    cycles_completed = 0
    start_time = time.time()

    try:
        logging.info(f"📍 Loading {TARGET_URL}")
        driver.get(TARGET_URL)
        time.sleep(12) # Wait for WASM to initialize

        while True:
            elapsed = (time.time() - start_time) / 60
            if cycles_completed >= MAX_CYCLES_PER_SESSION or elapsed >= MAX_MINUTES_PER_SESSION:
                logging.info("♻️ Session limit reached. Restarting browser...")
                break

            gc.collect()

            # --- IMPROVED LOGIN FLOW ---
            try:
                driver.implicitly_wait(5)
                if not driver.find_elements(By.XPATH, "//button[contains(.,'New Ship')]"):
                    logging.info("🔑 Login step: Finding Restore Link...")
                    
                    # 1. Click Restore using JS (more reliable in headless)
                    restore = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Restore')]")))
                    driver.execute_script("arguments[0].click();", restore)
                    
                    # 2. Key Input
                    logging.info("🔑 Login step: Entering Key...")
                    key_input = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.modal-window input")))
                    key_input.clear()
                    key_input.send_keys(ANONYMOUS_LOGIN_KEY)
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input',{bubbles:true}));", key_input)
                    
                    # 3. Submit
                    submit = driver.find_element(By.XPATH, "//button[text()='Submit']")
                    driver.execute_script("arguments[0].click();", submit)
                    time.sleep(4)
                    
                    # 4. Final Play Button
                    logging.info("🔑 Login step: Clicking Play Anonymously...")
                    play = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Play Anonymously')]")))
                    driver.execute_script("arguments[0].click();", play)
                    
                    # Wait for Menu to settle
                    wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(.,'New Ship')]")))
                    logging.info("✅ Login successful")
            except Exception as e:
                logging.warning(f"⚠️ Login failed: {str(e)[:50]}... Refreshing.")
                driver.refresh()
                time.sleep(10)
                continue

            # --- GAME CYCLE ---
            try:
                logging.info("🚢 Creating New Ship...")
                btn_new = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'New Ship')]")))
                driver.execute_script("arguments[0].click();", btn_new)
                time.sleep(2)

                btn_launch = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Launch')]")))
                driver.execute_script("arguments[0].click();", btn_launch)
                
                logging.info("🚀 In Game. Waiting 10s...")
                time.sleep(10)

                # EXIT
                driver.execute_script("""
                    const btn = document.querySelector('#exit_button') || 
                                [...document.querySelectorAll('button')].find(b => b.textContent.includes('Exit'));
                    if (btn) btn.click();
                """)
                
                # Wait for menu to return
                wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(.,'New Ship')]")))
                
                cycles_completed += 1
                logging.info(f"✨ Cycle {cycles_completed} complete.")
                time.sleep(2)

            except Exception as e:
                logging.warning(f"❌ Cycle error: {str(e)[:50]}")
                driver.refresh()
                time.sleep(8)

    except Exception:
        logging.error(f"🔥 Driver Crash: {traceback.format_exc()}")
    finally:
        driver.quit()

# --- FLASK ---
app = Flask(__name__)
@app.route("/")
def health(): return "Bot Running", 200

def main():
    # Start Flask on port 10000
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port, use_reloader=False), daemon=True).start()
    
    while True:
        try:
            start_bot()
            time.sleep(5)
        except Exception:
            time.sleep(20)

if __name__ == "__main__":
    main()
