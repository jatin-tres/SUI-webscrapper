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
st.set_page_config(page_title="SUI Scraper V20", layout="wide")
st.title("🔹 SUI Wallet Scraper (Keyboard & Visual Fix)")

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
    # Force 4K Resolution to ensure 'Time' and 'Pagination' are visible
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
                # Force click Activity tab
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
        
        # State Tracking
        previous_page_first_hash = None
        
        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Scroll to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Get Rows
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            if not rows:
                st.warning("No transactions found.")
                break
            
            # Save state
            current_first_hash = rows[0].text
            
            # Check if we are stuck on the same page (State Lock)
            if page_num > 0 and current_first_hash == previous_page_first_hash:
                st.warning("Data did not change. Retrying wait...")
                time.sleep(5)
                rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
                current_first_hash = rows[0].text
                if current_first_hash == previous_page_first_hash:
                    st.error("Pagination failed: Page did not update.")
                    break

            previous_page_first_hash = current_first_hash
            
            page_data = []
            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")
                    
                    # --- STRICT TIMESTAMP FIX ---
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    timestamp = "N/A"
                    
                    # Strategy: Take the LAST item in the row text. Timestamps are always last.
                    # This avoids matching "6h" inside a hash like "0x...a6h..."
                    text_parts = row_text.split('\n')
                    if not text_parts: text_parts = row_text.split()
                    
                    candidate = text_parts[-1].strip()
                    
                    # Check Candidate against Patterns
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", candidate)
                    age_match = re.search(r"^(\d+[dhmsy])$", candidate) # Exact match only (e.g. "6h", not "a6h")
                    
                    if date_match:
                         timestamp = candidate
                    elif age_match:
                        timestamp = candidate
                    else:
                        # Fallback: Check the second to last item
                        if len(text_parts) > 1:
                            candidate_2 = text_parts[-2].strip()
                            if re.search(r"(\d{4}-\d{2}-\d{2})", candidate_2):
                                timestamp = candidate_2
                    
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

            # --- PAGINATION (KEYBOARD + VISUAL) ---
            if page_num < max_pages - 1:
                page_changed = False
                
                try:
                    # Method 1: Keyboard Navigation (Right Arrow)
                    # Click the body to focus, then hit Right Arrow
                    driver.find_element(By.TAG_NAME, "body").click()
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_RIGHT)
                    time.sleep(3)
                    
                    # Check if changed
                    new_rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
                    if new_rows and new_rows[0].text != current_first_hash:
                        page_changed = True
                        st.info("Navigated via Keyboard.")
                    
                    # Method 2: Click any element that looks like a "Next" button
                    if not page_changed:
                        # Find buttons, divs, or links with specific attributes
                        candidates = driver.find_elements(By.XPATH, """
                            //button[contains(., '>')] | 
                            //button[contains(., 'Next')] |
                            //button[descendant::*[local-name()='svg']] |
                            //div[@role='button' and contains(., '>')] |
                            //a[contains(., '>')]
                        """)
                        
                        # Filter: Must be displayed and enabled
                        valid = [c for c in candidates if c.is_displayed()]
                        
                        # Try the LAST valid candidate (usually Bottom-Right Next)
                        if valid:
                            target = valid[-1]
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", target)
                            time.sleep(5)
                            
                            new_rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
                            if new_rows and new_rows[0].text != current_first_hash:
                                page_changed = True
                                st.info("Navigated via Click.")

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
