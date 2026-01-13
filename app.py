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
st.set_page_config(page_title="SUI Scraper V7", layout="wide")
st.title("🔹 SUI Wallet Scraper (Debug & Fix)")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Settings")
    wallet_address = st.text_input("Wallet Address", value="0xa36a0602be0fcbc59f7864c76238e5e502a1e13150090aab3c2063d34dde1d8a")
    max_pages = st.number_input("Max Pages", 1, 50, 3)
    debug_mode = st.checkbox("Show Debug Raw Data", value=False, help="Check this to see exactly what text the bot sees.")
    start_btn = st.button("🚀 Start Scraping", type="primary")

# --- BROWSER SETUP ---
def get_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

if start_btn:
    st.info(f"Scanning: {wallet_address}...")
    driver = None
    all_data = []
    
    try:
        driver = get_driver()
        url = f"https://suiscan.xyz/mainnet/account/{wallet_address}"
        driver.get(url)
        wait = WebDriverWait(driver, 20)
        
        # --- 1. FETCH BALANCE ---
        st.write("Fetching Balance...")
        time.sleep(8) # Extra wait for Cloud slowness
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            # Look for SUI Balance specifically
            match = re.search(r"SUI Balance\s*\n\s*([0-9,]+\.[0-9]+)", body_text)
            balance_found = match.group(1) if match else "Not Found"
            
            # Fallback: Search for the big number pattern if label is missing
            if balance_found == "Not Found":
                # Looks for number with 4+ decimal places (common for crypto)
                match_strict = re.search(r"(\d{2,3}(?:,\d{3})*\.\d{4,})", body_text)
                if match_strict: balance_found = match_strict.group(1)
                
            st.metric("SUI Balance", balance_found)
        except Exception as e:
            st.warning(f"Balance error: {e}")

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
            
            # Scroll to bottom to ensure elements render
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)

            # Find Rows
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            if not rows:
                st.warning("No transactions found.")
                break
            
            page_data = []
            
            # DEBUG: Print raw text of first row to understand what's wrong
            if debug_mode and page_num == 0 and rows:
                first_row_text = rows[0].find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]").text
                st.code(f"DEBUG - RAW ROW TEXT:\n{first_row_text}", language="text")

            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")
                    
                    # --- TIMESTAMP FIX (Length Logic) ---
                    # 1. Get the whole row text
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    
                    # 2. Split by newline to get columns
                    parts = row_text.split('\n')
                    
                    # 3. Filter out empty strings
                    clean_parts = [p.strip() for p in parts if p.strip()]
                    
                    # 4. The Timestamp/Age is usually the LAST element
                    # Logic: Hashes are Long (>20 chars). Age is Short (<15 chars).
                    # We look at the last item. If it's too long (like a hash), check the one before it.
                    timestamp = "N/A"
                    if clean_parts:
                        last_item = clean_parts[-1]
                        if len(last_item) < 20: 
                            timestamp = last_item
                        elif len(clean_parts) > 1 and len(clean_parts[-2]) < 20:
                            timestamp = clean_parts[-2]
                            
                    # 5. Regex Backup (for Age specific)
                    if timestamp == "N/A":
                        age_match = re.search(r"(\d+[dhms]\s*\d*[dhms]*)", row_text)
                        if age_match: timestamp = age_match.group(1)

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
                    # Strategy: Get ALL buttons on the page.
                    # The 'Next' button is chronologically the last interactive button in the DOM.
                    all_buttons = driver.find_elements(By.TAG_NAME, "button")
                    
                    # Filter for enabled buttons only
                    clickable_buttons = [b for b in all_buttons if b.is_enabled() and b.is_displayed()]
                    
                    clicked = False
                    if clickable_buttons:
                        # Try the last button
                        target = clickable_buttons[-1]
                        
                        # Verify it's not the "Connect Wallet" button (usually top right)
                        # Pagination buttons are usually at the bottom (high Y coordinate)
                        if target.location['y'] > 500: 
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", target)
                            clicked = True
                            time.sleep(5) # Wait for reload
                    
                    if not clicked:
                        # Fallback: Look for the specific 'pagination' container class
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
