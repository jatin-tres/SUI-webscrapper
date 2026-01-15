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
st.set_page_config(page_title="SUI Scraper V13", layout="wide")
st.title("🔹 SUI Wallet Scraper (Production Verified)")

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
    # Force 4K Resolution: Ensures 'Time' and 'Gas Fee' columns are always rendered
    options.add_argument('--window-size=3840,2160')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

if start_btn:
    st.info(f"Scanning: {wallet_address}...")
    driver = None
    all_data = []
    
    try:
        driver = get_driver()
        # Double-ensure window size
        driver.set_window_size(3840, 2160)
        
        url = f"https://suiscan.xyz/mainnet/account/{wallet_address}"
        driver.get(url)
        wait = WebDriverWait(driver, 30) # Extended wait for slow cloud network
        
        # --- 1. FETCH BALANCE ---
        st.write("Fetching Balance...")
        time.sleep(5) 
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            # Primary Regex: "Balance" followed by newline and number
            match = re.search(r"Balance\s*\n\s*([0-9,]+\.[0-9]+)", body_text)
            balance_found = match.group(1) if match else "Not Found"
            
            # Fallback Regex: Look for the specific SUI format (long decimals)
            if balance_found == "Not Found":
                match_strict = re.search(r"(\d{2,3}(?:,\d{3})*\.\d{4,})", body_text)
                if match_strict: balance_found = match_strict.group(1)
            
            st.metric("SUI Balance", balance_found)
        except:
            st.warning("Balance not found (UI layout might vary).")

        # --- 2. SWITCH TO ACTIVITY (THE CRITICAL FIX) ---
        st.write("Switching to Activity View...")
        
        # We perform a "Check-Click-Verify" loop.
        # We know we succeeded if we see "Gas Fee" (which is ONLY on the Activity tab)
        
        tab_verified = False
        attempts = 0
        while not tab_verified and attempts < 3:
            try:
                # Try clicking all likely candidates for the "Activity" tab
                # We use JS click to bypass any "overlay" or "element not clickable" errors
                potential_tabs = driver.find_elements(By.XPATH, "//div[contains(text(), 'Activity')] | //button[contains(text(), 'Activity')]")
                
                for tab in potential_tabs:
                    if tab.is_displayed():
                        driver.execute_script("arguments[0].click();", tab)
                        time.sleep(2) # Short wait for React to react

                # VERIFICATION: Check if the view changed
                page_source = driver.page_source
                if "Gas Fee" in page_source or "Digest" in page_source:
                    tab_verified = True
                    st.success("Verified: Activity View Loaded.")
                else:
                    attempts += 1
                    time.sleep(2)
            except:
                attempts += 1
        
        if not tab_verified:
            st.error("CRITICAL: Failed to switch to Activity tab. App is stuck on Portfolio view.")
            # Take a screenshot so you can see if it failed
            driver.save_screenshot("tab_error.png")
            st.image("tab_error.png")
            driver.quit()
            st.stop()

        # --- 3. WAIT FOR DATA POPULATION ---
        st.write("Waiting for transactions to populate...")
        try:
            # Wait specifically for a Transaction Hash link (begins with 0x... or similar)
            wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/tx/')]")))
            time.sleep(3) # Extra buffer for full table render
        except:
            st.error("Timed out waiting for data. The table appears empty.")
            driver.save_screenshot("empty_table.png")
            st.image("empty_table.png")
            driver.quit()
            st.stop()

        # --- 4. SCRAPE LOOP ---
        progress = st.progress(0)
        
        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Scroll to bottom to ensure footer/pagination loads
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Re-fetch rows every time
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            if not rows:
                st.warning("No transactions found on this page.")
                break
            
            page_data = []
            
            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")
                    
                    # --- TIMESTAMP LOGIC (Robust) ---
                    # 1. Grab the ENTIRE row text
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    
                    timestamp = "N/A"
                    
                    # Pattern A: Absolute Date (YYYY-MM-DD...)
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", row_text)
                    
                    # Pattern B: Relative Age (19h, 2d, 5m ago)
                    # Looks for digits followed immediately by 'd', 'h', 'm', 's'
                    age_match = re.search(r"\b(\d+[dhms])\b", row_text)
                    
                    if date_match:
                         # Try to grab the full timestamp if available
                         full_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                         timestamp = full_match.group(1) if full_match else date_match.group(1)
                    elif age_match:
                        # Extract the age component safely
                        parts = row_text.split()
                        for p in parts:
                            if re.search(r"^\d+[dhms]$", p):
                                timestamp = p
                                break
                    
                    # Hash Filter: If "timestamp" is just a long hash string, reject it
                    if len(timestamp) > 12 and not any(x in timestamp for x in ['-', ':', ' ']):
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

            # --- PAGINATION (Last Button Strategy) ---
            if page_num < max_pages - 1:
                try:
                    # Strategy: Find all enabled buttons. The "Next" button is almost always the LAST one.
                    all_buttons = driver.find_elements(By.TAG_NAME, "button")
                    valid_buttons = [b for b in all_buttons if b.is_enabled() and b.is_displayed()]
                    
                    clicked = False
                    if valid_buttons:
                        target = valid_buttons[-1]
                        
                        # Verify it's in the footer area (Y-coordinate check)
                        if target.location['y'] > 200:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", target)
                            clicked = True
                            time.sleep(5) # Mandatory wait for new data
                    
                    if not clicked:
                        # Fallback: Look for pagination class specifically
                        footer_btns = driver.find_elements(By.XPATH, "//div[contains(@class, 'pagination')]//button")
                        if footer_btns:
                             driver.execute_script("arguments[0].click();", footer_btns[-1])
                             clicked = True
                             time.sleep(5)

                    if not clicked:
                        st.warning("Next button not found (End of list).")
                        break
                        
                except Exception as e:
                    st.error(f"Pagination error: {e}")
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
