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
st.set_page_config(page_title="SUI Scraper Final", layout="wide")
st.title("🔹 SUI Wallet Scraper (Brute Force Mode)")

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
        wait = WebDriverWait(driver, 15)
        
        # --- 1. FETCH BALANCE ---
        st.write("Fetching Balance...")
        time.sleep(5) 
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            match = re.search(r"Balance\s*\n\s*([0-9,]+\.[0-9]+)", body_text)
            balance_found = match.group(1) if match else "Not Found"
            if balance_found == "Not Found":
                match_strict = re.search(r"(\d{2,}\.\d{5,})", body_text)
                if match_strict: balance_found = match_strict.group(1)
            st.metric("SUI Balance", balance_found)
        except:
            st.warning("Balance not found.")

        # --- 2. NAVIGATE TO ACTIVITY ---
        try:
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(3)
        except:
            st.write("Activity tab already active.")

        # --- 3. SCRAPE LOOP ---
        progress = st.progress(0)
        last_page_first_hash = "" # To check if page changed

        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Scroll to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Wait for rows
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            if not rows:
                st.warning("No transactions found.")
                break
            
            # --- STALE DATA CHECK ---
            # If we clicked 'Next' but the first hash is SAME as last page, wait longer
            retries = 0
            while retries < 5:
                current_first_hash = rows[0].text
                if current_first_hash == last_page_first_hash:
                    time.sleep(2) # Wait for table refresh
                    rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
                    retries += 1
                else:
                    break
            
            last_page_first_hash = rows[0].text # Update for next loop

            # --- DATA EXTRACTION ---
            page_data = []
            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")
                    
                    # Grab full text of the row container
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    
                    # Timestamp Logic: Date OR Age
                    # Priority 1: "2026-01-11 23:13:12"
                    ts_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                    if ts_match:
                        timestamp = ts_match.group(1)
                    else:
                        # Priority 2: "Age" format (e.g. 19h 55m, 2d)
                        # Look for digits followed by d/h/m at the END of the string
                        age_match = re.search(r"(\d+[dhms]\s*\d*[dhms]*)", row_text.split('\n')[-1])
                        timestamp = age_match.group(1) if age_match else row_text.split('\n')[-1]

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

            # --- PAGINATION (The "Brute Force" Click) ---
            if page_num < max_pages - 1:
                try:
                    # Find ANY button with a 'chevron-right' icon inside it
                    # This searches the whole DOM for the specific SVG path or class
                    next_btns = driver.find_elements(By.XPATH, "//button[descendant::*[contains(@class, 'chevron-right') or contains(@class, 'lucide-chevron-right') or contains(@data-icon, 'right')]]")
                    
                    clicked = False
                    if next_btns:
                        # The 'Next' button is invariably the LAST one in the list
                        target_btn = next_btns[-1]
                        
                        # Force scroll directly to it
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_btn)
                        time.sleep(1)
                        
                        if target_btn.is_enabled():
                            # JavaScript Click (Bypasses 'element not interactable')
                            driver.execute_script("arguments[0].click();", target_btn)
                            clicked = True
                            time.sleep(5) # Mandatory wait for new data load
                    
                    if not clicked:
                        # Fallback: Find the pagination container and click the last button child
                        footer_btns = driver.find_elements(By.XPATH, "//div[contains(@class, 'pagination')]//button")
                        if footer_btns:
                             driver.execute_script("arguments[0].click();", footer_btns[-1])
                             clicked = True
                             time.sleep(5)

                    if not clicked:
                        st.warning("Could not find or click Next button.")
                        break
                        
                except Exception as e:
                    st.error(f"Pagination failed: {e}")
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
