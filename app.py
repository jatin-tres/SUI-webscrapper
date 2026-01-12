import streamlit as st
import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Page Config ---
st.set_page_config(page_title="SUI Scraper", layout="wide")
st.title("🔹 SUI Wallet Scraper (Robust Fix)")

# --- Sidebar ---
with st.sidebar:
    st.header("Settings")
    wallet_address = st.text_input("Wallet Address", value="0xa36a0602be0fcbc59f7864c76238e5e502a1e13150090aab3c2063d34dde1d8a")
    max_pages = st.number_input("Max Pages", 1, 10, 3)
    start_btn = st.button("🚀 Start Scraping", type="primary")

# --- Cloud-Compatible Driver ---
def get_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    # Spoof User-Agent to prevent bot detection
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
        wait = WebDriverWait(driver, 20)
        
        # --- 1. SUI Balance (Regex Method) ---
        # This ignores HTML structure and just searches for the text pattern in the entire page source.
        st.write("Fetching Balance...")
        time.sleep(5)  # Give React time to render numbers
        
        page_source = driver.page_source
        # Regex explanation: Look for "SUI Balance", allow for newlines/spaces, capture the number/dots
        match = re.search(r"SUI Balance.*?([\d,]+\.\d+)", page_source, re.DOTALL)
        
        if match:
            balance_val = match.group(1).strip()
            st.metric("SUI Balance", balance_val)
        else:
            st.warning("Balance text found, but number format didn't match regex. Showing raw text snippet:")
            st.code(driver.find_element(By.TAG_NAME, "body").text[:500]) # Debug: Show what the bot sees
            balance_val = "N/A"

        # --- 2. Switch to Activity ---
        try:
            # Try to click Activity tab by text
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(3)
        except:
            st.write("Activity tab might already be active.")

        # --- 3. Scrape Table (Link Anchor Method) ---
        progress = st.progress(0)
        
        for i in range(max_pages):
            st.write(f"Scraping Page {i+1}...")
            time.sleep(2)
            
            # Find all Transaction Links (These are unique and always present)
            # We use them as "Anchors" to find the rest of the row data.
            tx_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            
            if not tx_links:
                st.warning("No transactions found on this page.")
                driver.save_screenshot("debug_no_rows.png")
                st.image("debug_no_rows.png")
                break
            
            for link in tx_links:
                try:
                    tx_hash = link.text
                    tx_url = link.get_attribute("href")
                    
                    # Find Timestamp: It is usually the LAST text element in the same row container.
                    # We go up to the row (tr or div) and find the last child.
                    try:
                        # Attempt 1: If it's a standard table row (tr)
                        row_time = link.find_element(By.XPATH, "./ancestor::tr//td[last()]").text
                    except:
                        # Attempt 2: If it's a div-based grid, go up 3-4 levels and find the last text div
                        row_time = link.find_element(By.XPATH, "./ancestor::div[contains(@class, 'row') or @role='row']//div[last()]").text
                    
                    if tx_hash:
                        all_data.append({
                            "Wallet Balance": balance_val,
                            "Transaction Hash": tx_hash,
                            "Time (Age)": row_time,
                            "Link": tx_url
                        })
                except Exception as e:
                    continue # Skip broken rows

            # Pagination: Click Next
            try:
                # Find the arrow button. Usually generic. We look for the last button in the pagination area.
                next_btn = driver.find_elements(By.XPATH, "//button[contains(@class, 'pagination') or .//svg]")[-1]
                if not next_btn.is_enabled():
                    break
                driver.execute_script("arguments[0].click();", next_btn)
                progress.progress((i + 1) / max_pages)
                time.sleep(2)
            except:
                break # No next button found

        progress.progress(100)
        
        # --- Results ---
        if all_data:
            st.success(f"Collected {len(all_data)} Transactions!")
            df = pd.DataFrame(all_data)
            st.dataframe(df)
            st.download_button("Download CSV", df.to_csv(index=False).encode('utf-8'), "sui_data.csv")
        else:
            st.error("No data collected. Check the screenshot below to see what the scraper saw.")
            driver.save_screenshot("final_debug.png")
            st.image("final_debug.png")

    except Exception as e:
        st.error(f"Critical Error: {e}")
    finally:
        if driver: driver.quit()
