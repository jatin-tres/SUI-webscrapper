import streamlit as st
import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
st.set_page_config(page_title="SUI Scraper V21", layout="wide")
st.title("🔹 SUI Wallet Scraper (Coordinate-Based Fix)")

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
            st.error("Failed to switch tabs. Please restart.")
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
        current_first_hash = ""
        
        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Scroll to bottom to ensure footer is interactable
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Get Rows
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            if not rows:
                st.warning("No transactions found.")
                break
            
            # State Check
            if page_num > 0:
                if rows[0].text == current_first_hash:
                    st.warning("Data is stale (same as last page). Waiting...")
                    time.sleep(5)
                    rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
                    if rows[0].text == current_first_hash:
                         st.error("Pagination failed: Page did not update.")
                         break
            
            current_first_hash = rows[0].text
            
            page_data = []
            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")
                    
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    timestamp = "N/A"
                    
                    # --- FIXED TIMESTAMP REGEX ---
                    # 1. Date (2026-01-11)
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", row_text)
                    
                    # 2. Age (Strict Word Boundary): \b ensures we don't match inside a hash
                    # Matches " 6h " or " 5m " but NOT "a6h"
                    age_match = re.search(r"\b(\d+[dhmsy])\b", row_text)
                    
                    if date_match:
                         # Try to expand to full time
                         full = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                         timestamp = full.group(1) if full else date_match.group(1)
                    elif age_match:
                        timestamp = age_match.group(1)
                    
                    # Final Safety Check: If it still looks like a hash, kill it
                    if len(timestamp) > 15 and " " not in timestamp and "-" not in timestamp:
                         timestamp = "N/A"
                    
                    if tx_hash:
                        page_data.append({
                            "Transaction Hash": tx_hash,
                            "Timestamp": timestamp,
                            "Link": tx_url
                        })
                except:
                    continue
            
            all_data.extend(page_data)
            st.success(f"Collected {len(page_data)} items from Page {page_num + 1}")

            # --- PAGINATION (The Bottom-Right Rule) ---
            if page_num < max_pages - 1:
                page_changed = False
                try:
                    # 1. Find ALL buttons
                    buttons = driver.find_elements(By.TAG_NAME, "button")
                    
                    # 2. Filter: Must be visible and enabled
                    valid_buttons = []
                    for b in buttons:
                        if b.is_displayed() and b.is_enabled():
                            # Must be in the lower half of the page (Footer area)
                            if b.location['y'] > 500:
                                valid_buttons.append(b)
                    
                    # 3. Sort by X coordinate (Left to Right). The "Next" button is furthest right.
                    if valid_buttons:
                        # Sort buttons by their X location (ascending)
                        valid_buttons.sort(key=lambda x: x.location['x'])
                        
                        # The very last button in this list is the Bottom-Right-most button.
                        target = valid_buttons[-1]
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", target)
                        
                        # Wait for reload
                        time.sleep(5)
                        
                        # Verify
                        new_rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
                        if new_rows and new_rows[0].text != current_first_hash:
                            page_changed = True

                except Exception as e:
                    st.error(f"Pagination error: {e}")
                
                if not page_changed:
                    st.warning("Could not switch to next page (End of list).")
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
