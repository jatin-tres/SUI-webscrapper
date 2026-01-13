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
st.set_page_config(page_title="SUI Scraper V10", layout="wide")
st.title("🔹 SUI Wallet Scraper (Tab Switch Fix)")

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
    # Force 4K to ensure 'Time' column is rendered
    options.add_argument('--window-size=3840,2160')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

if start_btn:
    st.info(f"Scanning: {wallet_address}...")
    driver = None
    all_data = []
    
    try:
        driver = get_driver()
        # Force 4K resolution
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
            st.warning("Balance not found.")

        # --- 2. FORCE NAVIGATE TO ACTIVITY ---
        st.write("Switching to Activity Tab...")
        tab_switched = False
        
        # Try multiple selectors to click the tab
        selectors = [
            "//div[text()='Activity']", 
            "//span[text()='Activity']",
            "//button[contains(., 'Activity')]",
            "//div[contains(@class, 'tab') and contains(., 'Activity')]"
        ]
        
        for _ in range(3): # Retry loop
            for xpath in selectors:
                try:
                    tabs = driver.find_elements(By.XPATH, xpath)
                    for tab in tabs:
                        # Only click visible tabs
                        if tab.is_displayed():
                            driver.execute_script("arguments[0].click();", tab)
                            time.sleep(2)
                            
                            # VERIFY: Check if "Gas Fee" or "Type" header appears (Unique to Activity)
                            body_check = driver.find_element(By.TAG_NAME, "body").text
                            if "Gas Fee" in body_check or "Digest" in body_check:
                                tab_switched = True
                                break
                    if tab_switched: break
                except:
                    continue
            if tab_switched: break
            time.sleep(1)
            
        if not tab_switched:
            st.error("Could not switch to Activity Tab. Stuck on Portfolio.")
            # Stop here to prevent empty CSV
            driver.quit()
            st.stop()
        else:
            st.success("Successfully switched to Activity Tab!")

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
                    
                    # --- TIMESTAMP LOGIC ---
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    
                    timestamp = "N/A"
                    
                    # Regex for Date (2026-...)
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", row_text)
                    # Regex for Age (19h, 2d, 5m)
                    age_match = re.search(r"\b(\d+[dhms])\b", row_text)
                    
                    if date_match:
                         full_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                         timestamp = full_match.group(1) if full_match else date_match.group(1)
                    elif age_match:
                        # Safe extract of age
                        parts = row_text.split()
                        for p in parts:
                            if re.search(r"^\d+[dhms]$", p):
                                timestamp = p
                                break
                    
                    # Sanity Check
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

            # --- PAGINATION ---
            if page_num < max_pages - 1:
                try:
                    all_buttons = driver.find_elements(By.TAG_NAME, "button")
                    valid_buttons = [b for b in all_buttons if b.is_enabled() and b.is_displayed()]
                    
                    clicked = False
                    if valid_buttons:
                        target = valid_buttons[-1]
                        if target.location['y'] > 200:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", target)
                            clicked = True
                            time.sleep(5)
                    
                    if not clicked:
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
