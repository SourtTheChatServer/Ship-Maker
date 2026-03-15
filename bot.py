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

# --- CONFIG ---
TARGET_URL = 'https://drednot.io/'
# Use Environment Variable 'BOT_KEY' on Render for security
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
    # Optimize for Render's tiny RAM
    opts.add_argument("--js-flags=--max-old-space-size=128")
    opts.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    
    return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=opts)

def start_bot():
    driver = setup_driver()
    try:
        logging.info(f"📍 Loading {TARGET_URL}")
        driver.get(TARGET_URL)
        
        # Give Render a lot of time to load the WASM engine
        logging.info("⏳ Waiting 30s for game engine...")
        time.sleep(30)

        # CHECK IF PAGE LOADED
        res = driver.execute_script("return {buttons: document.querySelectorAll('button').length, canvas: !!document.querySelector('canvas')}")
        logging.info(f"🔍 Page Check: {res['buttons']} buttons found, Canvas exists: {res['canvas']}")

        # MASTER SCRIPT: Handles Accept -> Restore -> Login -> Your Cycle
        master_script = f"""
        (async function() {{
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            const findAndClick = (txt, tag = '*') => {{
                const el = [...document.querySelectorAll(tag)].find(e => e.textContent.includes(txt));
                if (el) {{ el.click(); return true; }}
                return false;
            }};

            console.log("Master Script Started");

            while (true) {{
                // 1. Handle Notice/Accept
                if (findAndClick("Accept", "button")) {{
                    console.log("Clicked Accept");
                    await sleep(2000);
                }}

                // 2. Handle Login if menu isn't visible
                const menuVisible = [...document.querySelectorAll('button')].some(b => b.textContent.includes('New Ship'));
                
                if (!menuVisible) {{
                    if (findAndClick("Restore", "a")) {{
                        console.log("Clicked Restore");
                        await sleep(2000);
                        const input = document.querySelector('.modal-window input');
                        if (input) {{
                            input.value = "{ANONYMOUS_LOGIN_KEY}";
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            await sleep(500);
                            findAndClick("Submit", "button");
                            console.log("Submitted Key");
                            await sleep(3000);
                        }}
                    }}
                    if (findAndClick("Play Anonymously", "button")) {{
                        console.log("Clicked Play");
                        await sleep(5000);
                    }}
                }}

                // 3. YOUR ORIGINAL SHIP CYCLE CODE
                if (menuVisible) {{
                    console.log("Menu active. Starting ship cycle.");
                    findAndClick("New Ship", "button");
                    await sleep(2000);
                    findAndClick("Launch", "button");
                    console.log("Launched Ship");
                    
                    await sleep(15000); // Stay in game

                    const exitBtn = document.querySelector("#exit_button") || 
                                    [...document.querySelectorAll('button')].find(b => b.textContent.includes('Exit'));
                    if (exitBtn) exitBtn.click();
                    console.log("Exited Ship");
                    await sleep(5000);
                }}

                await sleep(5000); // Loop delay
            }}
        }})();
        """

        logging.info("💉 Injecting Master Control Script...")
        driver.execute_script(master_script)

        # Keep Python alive while the JS runs in the browser
        while True:
            # Check every 60s if the browser is still responsive
            driver.title
            time.sleep(60)

    except Exception as e:
        logging.error(f"🔥 Driver Crash: {e}")
    finally:
        logging.info("🧹 Cleaning up browser...")
        driver.quit()

# --- FLASK ---
app = Flask(__name__)
@app.route("/")
def health(): return "Bot Running", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port, use_reloader=False), daemon=True).start()
    while True:
        try:
            start_bot()
        except:
            time.sleep(10)
