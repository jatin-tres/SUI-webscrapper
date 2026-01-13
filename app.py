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
st.set_page_config(page_title="SUI Scraper V9", layout="wide")
st.title("🔹 SUI Wallet Scraper (Final Logic)")

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
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

if start_btn:
    st.info(f"Scanning: {wallet_address}...")
    driver = None
    all_data = []
    
    try:
        driver = get_driver()
        # CRITICAL: Force 4K resolution AFTER driver start to ensure columns render
        driver.set_window_size(3840, 2160)
        
        url = f"https://suiscan.xyz/mainnet/account/{wallet_address}"
        driver.get(url)
        wait = WebDriverWait(driver, 20)
        
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
            st.warning("Balance not found (Layout might have shifted).")

        # --- 2. NAVIGATE TO ACTIVITY ---
        try:
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(5)
        except:
            st.write("Activity tab might already be active.")

        # --- 3. SCRAPE LOOP ---
        progress = st.progress(0)
        
        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Scroll to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)

            # Find Rows
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            if not rows:
                st.warning("No transactions found.")
                break
            
            page_data = []
            
            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")
                    
                    # --- TIMESTAMP LOGIC (Strict Filtering) ---
                    # 1. Get row text
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    
                    timestamp = "N/A"
                    
                    # Check for "Age" pattern (e.g., 19h 55m, 2d)
                    # We regex for digits followed by time units
                    age_match = re.search(r"\b(\d+[dhms])\b", row_text)
                    
                    # Check for Date pattern
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", row_text)
                    
                    if date_match:
                         # Try to grab full date string
                         full_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                         timestamp = full_match.group(1) if full_match else date_match.group(1)
                    elif age_match:
                        # Grab the age string (e.g. 19h 55m)
                        # We split the row text and find the part that matches the age regex
                        parts = row_text.split()
                        for p in parts:
                            if re.search(r"\d+[dhms]", p):
                                timestamp = p
                                break
                    
                    # --- CRITICAL SANITY CHECK ---
                    # If "timestamp" looks like the hash suffix (random chars), kill it.
                    # Hashes usually have no specific time units and are long.
                    if len(timestamp) > 10 and not any(x in timestamp for x in ['-', ':', ' ']):
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
                    # Find all buttons
                    all_buttons = driver.find_elements(By.TAG_NAME, "button")
                    # Filter for visible, enabled buttons
                    valid_buttons = [b for b in all_buttons if b.is_enabled() and b.is_displayed()]
                    
                    clicked = False
                    if valid_buttons:
                        # The "Next" button is almost always the LAST valid button on the page
                        target = valid_buttons[-1]
                        
                        # Verify Y-coordinate (Pagination is at bottom, >500px usually)
                        if target.location['y'] > 200:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", target)
                            clicked = True
                            time.sleep(5)
                    
                    if not clicked:
                        # Fallback: specific pagination class
                        footer_btns = driver.find_elements(By.XPATH, "//div[contains(@class, 'pagination')]//button")
                        if footer_btns:
                             driver.execute_script("arguments[0].click();", footer_btns[-1])
                             clicked = True
                             time.sleep(5)

                    if not clicked:
                        st.warning("Next button not found.")
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
