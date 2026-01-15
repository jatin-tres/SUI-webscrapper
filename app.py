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
st.set_page_config(page_title="SUI Scraper V16", layout="wide")
st.title("🔹 SUI Wallet Scraper (State-Locked Pagination)")

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
        current_page_hash = ""  # Stores the first hash of the current page
        
        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Ensure we have new data before scraping
            # If this is NOT the first page, we wait until the top hash CHANGES
            if page_num > 0:
                retries = 0
                data_refreshed = False
                while retries < 10: # Wait up to 10 seconds
                    rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
                    if rows:
                        new_top_hash = rows[0].text
                        if new_top_hash != current_page_hash:
                            data_refreshed = True
                            break # Data has changed!
                    time.sleep(1)
                    retries += 1
                
                if not data_refreshed:
                    st.warning(f"Page {page_num + 1} did not load new data (Timed out). Stopping.")
                    break

            # Scroll to bottom to ensure full render
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # --- EXTRACT DATA ---
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            if not rows:
                st.warning("No transactions found.")
                break
            
            # Update current hash state
            current_page_hash = rows[0].text
            
            page_data = []
            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")
                    
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    timestamp = "N/A"
                    
                    # Robust Timestamp Regex
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                    age_match = re.search(r"(\d+\s*[dhmsy]\s*(?:ago)?)", row_text)
                    
                    if date_match:
                         timestamp = date_match.group(1)
                    elif age_match:
                        timestamp = age_match.group(1)
                    
                    if len(timestamp) > 20 and " " not in timestamp:
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

            # --- CLICK NEXT ---
            if page_num < max_pages - 1:
                try:
                    # Strategy: Click the LAST visible button in the DOM
                    all_buttons = driver.find_elements(By.TAG_NAME, "button")
                    visible_buttons = [b for b in all_buttons if b.is_displayed()]
                    
                    clicked = False
                    if visible_buttons:
                        target = visible_buttons[-1]
                        # Verify it's in the footer area
                        if target.location['y'] > 200:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", target)
                            clicked = True
                    
                    if not clicked:
                        # Fallback: Look for SVG arrows
                        svg_btns = driver.find_elements(By.XPATH, "//button[descendant::*[local-name()='svg']]")
                        if svg_btns:
                            driver.execute_script("arguments[0].click();", svg_btns[-1])
                            clicked = True
                    
                    if not clicked:
                        st.warning("Next button not found.")
                        break
                        
                except Exception as e:
                    st.error(f"Pagination click failed: {e}")
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
