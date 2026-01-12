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
st.set_page_config(page_title="SUI Scraper Pro", layout="wide")
st.title("🔹 SUI Wallet Scraper (QA Verified)")

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
    # 4K Resolution ensuring all columns (like Time) are rendered
    options.add_argument('--window-size=3840,2160')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

# --- HELPER: FIND BALANCE IN RAW TEXT ---
def extract_balance_from_body(driver):
    """Scans the entire page text for 'SUI Balance' and the number following it."""
    try:
        text = driver.find_element(By.TAG_NAME, "body").text
        # Regex: Look for 'SUI Balance' followed by newlines/spaces, then a number with decimals
        match = re.search(r"SUI Balance\s*\n\s*([\d,]+\.\d+)", text)
        if match:
            return match.group(1)
        
        # Fallback: Look for just the number if it appears differently
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if "SUI Balance" in line:
                # Check the next 3 lines for a number
                for j in range(1, 4):
                    if i + j < len(lines) and re.match(r"[\d,]+\.\d+", lines[i+j]):
                        return lines[i+j]
        return "Not Found"
    except:
        return "Error"

if start_btn:
    st.info(f"Scanning: {wallet_address}...")
    driver = None
    all_data = []
    
    try:
        driver = get_driver()
        url = f"https://suiscan.xyz/mainnet/account/{wallet_address}"
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        
        # 1. FETCH BALANCE (Raw Text Method)
        st.write("Fetching Balance...")
        time.sleep(5) # Wait for React to render
        balance = extract_balance_from_body(driver)
        st.metric("SUI Balance", balance)

        # 2. NAVIGATE TO ACTIVITY
        try:
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(3)
        except:
            st.write("Activity tab might already be active.")

        # 3. SCRAPE LOOP
        progress = st.progress(0)
        last_first_hash = "" # To detect if page actually changed

        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Scroll down to trigger lazy loading and reveal 'Next' button
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # --- STALE CHECK ---
            # Wait until the first row is DIFFERENT from the last page's first row
            # This prevents capturing Page 1 data repeatedly
            retries = 0
            current_first_hash = ""
            rows = []
            
            while retries < 10:
                rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
                if rows:
                    current_first_hash = rows[0].text
                    if current_first_hash != last_first_hash:
                        break # New data loaded!
                time.sleep(1)
                retries += 1
            
            if not rows:
                st.warning("No transactions found.")
                break
                
            last_first_hash = current_first_hash # Update for next loop

            # --- EXTRACT DATA ---
            page_data = []
            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")
                    
                    # Grab the whole row text to find the date
                    # We use 'ancestor' to get the row container
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    
                    # Robust Date Regex (YYYY-MM-DD HH:MM:SS)
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                    timestamp = date_match.group(1) if date_match else "N/A"

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
                    # Find the SVG arrow specifically
                    # We look for the button that holds the 'chevron-right' or 'right' icon
                    next_btns = driver.find_elements(By.XPATH, "//button[descendant::*[name()='svg' and (contains(@data-icon, 'right') or contains(@class, 'chevron-right'))]]")
                    
                    if next_btns:
                        target_btn = next_btns[-1] # Usually the last one
                        if target_btn.is_enabled():
                            driver.execute_script("arguments[0].click();", target_btn)
                            time.sleep(2) # Short wait, the 'Stale Check' loop above handles the real waiting
                        else:
                            st.write("Next button disabled (End of List).")
                            break
                    else:
                        st.write("Next button not found.")
                        break
                except Exception as e:
                    st.error(f"Pagination failed: {e}")
                    break
            
            progress.progress((page_num + 1) / max_pages)

        # --- FINAL RESULTS ---
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
