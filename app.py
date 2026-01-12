import streamlit as st
import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Page Setup ---
st.set_page_config(page_title="SUI Scraper V3", layout="wide")
st.title("🔹 SUI Wallet Scraper (Final Fixed Version)")

# --- Sidebar ---
with st.sidebar:
    st.header("Settings")
    wallet_address = st.text_input("Wallet Address", value="0xa36a0602be0fcbc59f7864c76238e5e502a1e13150090aab3c2063d34dde1d8a")
    max_pages = st.number_input("Max Pages", 1, 50, 3)
    start_btn = st.button("🚀 Start Scraping", type="primary")

# --- Optimized Driver ---
def get_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
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
        
        # --- 1. Get Balance (Robust Line Check) ---
        st.write("Fetching Balance...")
        time.sleep(5) 
        
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.split('\n')
            balance_val = "Not Found"
            for index, line in enumerate(body_text):
                # Search for "Balance" and grab the very next line if it looks like a number
                if "Balance" in line and "SUI" in line:
                    if index + 1 < len(body_text):
                        possible_bal = body_text[index + 1]
                        if any(char.isdigit() for char in possible_bal):
                            balance_val = possible_bal
                            break
            st.metric("SUI Balance", balance_val)
        except:
            st.warning("Could not read balance, proceeding...")

        # --- 2. Switch to Activity ---
        try:
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(3)
        except:
            st.write("Activity tab already active.")

        # --- 3. Scrape Loop ---
        progress = st.progress(0)
        
        for i in range(max_pages):
            st.write(f"📄 Scraping Page {i+1}...")
            
            # Scroll to bottom to ensure 'Next' arrow is in view
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Find all rows by looking for the Hash Link (Blue Link)
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            
            if not rows:
                st.warning("No transactions found on this page.")
                break
            
            page_count = 0
            for row_link in rows:
                try:
                    # 1. Get Hash & Link
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")

                    # 2. Get Timestamp (STRICT REGEX)
                    # We go up to the row container and get all text, then search for a date.
                    # This prevents grabbing the hash end-string like '33uXL...'
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    
                    # Regex for 'YYYY-MM-DD HH:MM:SS'
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                    
                    if date_match:
                        timestamp = date_match.group(1)
                    else:
                        timestamp = "N/A" # Leave blank if no real date found

                    if tx_hash:
                        all_data.append({
                            "Transaction Hash": tx_hash,
                            "Timestamp": timestamp,
                            "Link": tx_url
                        })
                        page_count += 1
                except:
                    continue
            
            st.success(f"Collected {page_count} transactions from Page {i+1}")

            # --- Pagination (Next Arrow Fix) ---
            if i < max_pages - 1:
                try:
                    # Strategy 1: Find the SVG arrow specifically (Right Chevron)
                    # We look for an SVG inside a button/div that is NOT disabled
                    next_arrow = driver.find_elements(By.XPATH, "//*[name()='svg' and (contains(@data-icon, 'right') or contains(@class, 'chevron-right'))]")
                    
                    clicked = False
                    if next_arrow:
                        # usually the last arrow is 'Next'
                        target = next_arrow[-1]
                        # Click the parent button, not the SVG itself
                        parent_btn = target.find_element(By.XPATH, "./ancestor::button | ./ancestor::div[@role='button']")
                        
                        if parent_btn.is_enabled():
                            driver.execute_script("arguments[0].click();", parent_btn)
                            clicked = True
                    
                    # Strategy 2: Fallback to 'Last Button' in pagination container
                    if not clicked:
                        pagination_btns = driver.find_elements(By.XPATH, "//button[contains(@class, 'pagination')]")
                        if pagination_btns:
                             driver.execute_script("arguments[0].click();", pagination_btns[-1])
                             clicked = True

                    if clicked:
                        time.sleep(4) # Wait for table reload
                    else:
                        st.warning("Next button not found or disabled.")
                        break
                except Exception as e:
                    st.write(f"Pagination error: {e}")
                    break
            
            progress.progress((i + 1) / max_pages)

        # --- Results ---
        if all_data:
            st.success(f"✅ Total Collected: {len(all_data)} Transactions")
            df = pd.DataFrame(all_data)
            st.dataframe(df)
            st.download_button("Download CSV", df.to_csv(index=False).encode('utf-8'), "sui_data.csv")
        else:
            st.error("No data collected.")

    except Exception as e:
        st.error(f"Critical Error: {e}")
    finally:
        if driver: driver.quit()
