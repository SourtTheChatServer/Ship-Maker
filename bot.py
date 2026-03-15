import os
import time
import logging
import threading
import gc
import sys
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

logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S'
)

def setup_driver():
    opts = Options()
    opts.binary_location = "/usr/bin/chromium" 
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,720")
    # Low memory optimization
    opts.add_argument("--js-flags=--max-old-space-size=128")
    opts.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=opts)

def start_bot():
    driver = setup_driver()
    # High timeout for Render's slow CPU
    wait = WebDriverWait(driver, 30) 

    try:
        logging.info(f"📍 Loading {TARGET_URL}")
        driver.get(TARGET_URL)
        time.sleep(15) # Wait for initial engine load

        while True:
            gc.collect()
            
            # --- 1. HANDLE "ACCEPT" MODAL (If it exists) ---
            accept_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept')]")
            if accept_btns:
                logging.info("✅ Notice found. Clicking Accept...")
                driver.execute_script("arguments[0].click();", accept_btns[0])
                time.sleep(3)

            # --- 2. HANDLE LOGIN / RESTORE (If menu isn't visible) ---
            # If 'New Ship' isn't there, we need to handle the login/restore process
            menu_present = driver.find_elements(By.XPATH, "//button[contains(.,'New Ship')]")
            
            if not menu_present:
                logging.info("🔑 Menu not found. Checking for Login/Restore...")
                
                # Check for Restore Link
                restore_links = driver.find_elements(By.XPATH, "//a[contains(text(),'Restore')]")
                if restore_links:
                    logging.info("🔑 Clicking Restore...")
                    driver.execute_script("arguments[0].click();", restore_links[0])
                    time.sleep(2)

                    # Find input, type key, and trigger 'input' event to enable Submit button
                    try:
                        key_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".modal-window input")))
                        key_input.send_keys(ANONYMOUS_LOGIN_KEY)
                        # This enables the 'Submit' button
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", key_input)
                        time.sleep(1)

                        submit_btn = driver.find_element(By.XPATH, "//button[text()='Submit']")
                        driver.execute_script("arguments[0].click();", submit_btn)
                        logging.info("🔑 Submit clicked.")
                        time.sleep(3)
                    except Exception as e:
                        logging.warning(f"⚠️ Key input failed: {e}")

                # Check for Play Anonymously (Final step of login)
                play_btns = driver.find_elements(By.XPATH, "//button[contains(text(),'Play Anonymously')]")
                if play_btns:
                    logging.info("🔑 Clicking Play Anonymously...")
                    driver.execute_script("arguments[0].click();", play_btns[0])
                    time.sleep(5)

            # --- 3. SHIP CREATION CYCLE (Runs as long as New Ship is visible) ---
            try:
                # Fast check for menu
                driver.implicitly_wait(2)
                if driver.find_elements(By.XPATH, "//button[contains(.,'New Ship')]"):
                    logging.info("🚢 Creating Ship...")
                    
                    btn_new = driver.find_element(By.XPATH, "//button[contains(.,'New Ship')]")
                    driver.execute_script("arguments[0].click();", btn_new)
                    time.sleep(2)

                    btn_launch = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Launch')]")))
                    driver.execute_script("arguments[0].click();", btn_launch)
                    
                    logging.info("🚀 In Game - Holding for 15s...")
                    time.sleep(15)

                    logging.info("🚪 Exiting...")
                    driver.execute_script("""
                        const exit = document.querySelector('#exit_button') || 
                                     [...document.querySelectorAll('button')].find(b => b.textContent.includes('Exit'));
                        if (exit) exit.click();
                    """)
                    time.sleep(5) # Wait for return to menu
                else:
                    logging.warning("⏳ Menu not visible yet, waiting...")
                    time.sleep(5)
                    
            except Exception as e:
                logging.warning(f"❌ Cycle step failed: {str(e)[:50]}")
                driver.refresh()
                time.sleep(10)

    except Exception as e:
        logging.error(f"🔥 Driver Crash: {e}")
    finally:
        driver.quit()

# --- FLASK ---
app = Flask(__name__)
@app.route("/")
def health(): return "Bot Running", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port, use_reloader=False), daemon=True).start()
    while True:
        start_bot()
        time.sleep(5)
