import streamlit as st
import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
st.set_page_config(page_title="SUI Scraper V19", layout="wide")
st.title("🔹 SUI Wallet Scraper (Brute Force Pagination)")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Settings")
    wallet_address = st.text_input("Wallet Address", value="0xa36a0602be0fcbc59f7864c76238e5e502a1e13150090aab3c2063d34dde1d8a")
    max_pages = st.number_input("Max Pages", 1, 50, 3)
    start_btn = st.button("🚀 Start Scraping", type="primary")

# --- BROWSER SETUP ---
def get_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=3840,2160')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

def get_current_first_hash(driver):
    """Helper to get the top transaction hash currently on screen"""
    try:
        rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
        if rows:
            return rows[0].text
    except:
        return None
    return None

if start_btn:
    st.info(f"Scanning: {wallet_address}...")
    driver = None
    all_data = []
    
    try:
        driver = get_driver()
        driver.set_window_size(3840, 2160)
        
        url = f"https://suiscan.xyz/mainnet/account/{wallet_address}"
        driver.get(url)
        wait = WebDriverWait(driver, 30)
        
        # --- 1. FETCH BALANCE ---
        st.write("Fetching Balance...")
        time.sleep(5) 
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            match = re.search(r"Balance\s*\n\s*([0-9,]+\.[0-9]+)", body_text)
            balance_found = match.group(1) if match else "Not Found"
            if balance_found == "Not Found":
                match_strict = re.search(r"(\d{2,3}(?:,\d{3})*\.\d{4,})", body_text)
                if match_strict: balance_found = match_strict.group(1)
            st.metric("SUI Balance", balance_found)
        except:
            st.warning("Balance not found.")

        # --- 2. SWITCH TO ACTIVITY ---
        st.write("Switching to Activity View...")
        tab_verified = False
        attempts = 0
        while not tab_verified and attempts < 3:
            try:
                potential_tabs = driver.find_elements(By.XPATH, "//div[contains(text(), 'Activity')] | //button[contains(text(), 'Activity')]")
                for tab in potential_tabs:
                    if tab.is_displayed():
                        driver.execute_script("arguments[0].click();", tab)
                        time.sleep(2)
                if "Gas Fee" in driver.page_source or "Digest" in driver.page_source:
                    tab_verified = True
                    st.success("Verified: Activity View Loaded.")
                else:
                    attempts += 1
                    time.sleep(2)
            except:
                attempts += 1
        
        if not tab_verified:
            st.error("Failed to switch tabs.")
            driver.quit()
            st.stop()

        # --- 3. WAIT FOR DATA ---
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/tx/')]")))
            time.sleep(3)
        except:
            st.error("Table is empty.")
            driver.quit()
            st.stop()

        # --- 4. SCRAPE LOOP ---
        progress = st.progress(0)
        
        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Scroll to bottom to render footer
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Get Rows
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            if not rows:
                st.warning("No transactions found.")
                break
            
            # MEMORIZE CURRENT STATE
            current_page_first_hash = rows[0].text
            
            # EXTRACT DATA
            page_data = []
            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")
                    
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    timestamp = "N/A"
                    
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                    age_match = re.search(r"(\d+\s*[dhmsy]\s*(?:ago)?)", row_text)
                    
                    if date_match:
                         timestamp = date_match.group(1)
                    elif age_match:
                        timestamp = age_match.group(1)
                    
                    if len(timestamp) > 20 and " " not in timestamp: timestamp = "N/A"
                    
                    if tx_hash:
                        page_data.append({"Transaction Hash": tx_hash, "Timestamp": timestamp, "Link": tx_url})
                except:
                    continue
            
            all_data.extend(page_data)
            st.success(f"Collected {len(page_data)} items from Page {page_num + 1}")

            # --- PAGINATION: BRUTE FORCE ---
            if page_num < max_pages - 1:
                page_changed = False
                
                # LIST OF CANDIDATES: Find EVERY possible button that could be "Next"
                # 1. Buttons with SVG (Icons)
                # 2. Buttons with text '>' or 'Next'
                # 3. Buttons inside pagination containers
                candidates = []
                candidates.extend(driver.find_elements(By.XPATH, "//button[descendant::*[local-name()='svg']]"))
                candidates.extend(driver.find_elements(By.XPATH, "//button[contains(., '>')]"))
                candidates.extend(driver.find_elements(By.XPATH, "//div[contains(@class, 'pagination')]//button"))
                
                # Filter duplicates and visible only
                unique_candidates = []
                seen = set()
                for btn in candidates:
                    if btn not in seen and btn.is_displayed() and btn.is_enabled():
                        unique_candidates.append(btn)
                        seen.add(btn)
                
                # Try clicking them REVERSE (Bottom-Right buttons are usually last in DOM)
                for btn in reversed(unique_candidates):
                    try:
                        # Skip "Connect Wallet" (usually at top)
                        if btn.location['y'] < 100: continue
                        
                        # Click
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(3) # Wait for load
                        
                        # CHECK: Did it work?
                        new_hash = get_current_first_hash(driver)
                        if new_hash and new_hash != current_page_first_hash:
                            st.info("Next page loaded successfully.")
                            page_changed = True
                            break # It worked! Stop clicking.
                    except:
                        continue
                
                if not page_changed:
                    st.warning("Could not switch to next page (tried all buttons).")
                    break
            
            progress.progress((page_num + 1) / max_pages)

        # --- RESULTS ---
        if all_data:
            st.success(f"✅ Scraping Complete! Total: {len(all_data)}")
            df = pd.DataFrame(all_data)
            st.dataframe(df)
            st.download_button("Download CSV", df.to_csv(index=False).encode('utf-8'), "sui_data.csv")
        else:
            st.error("No data collected.")

    except Exception as e:
        st.error(f"Critical Error: {e}")
    finally:
        if driver: driver.quit()
