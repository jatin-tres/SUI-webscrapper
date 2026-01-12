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
st.set_page_config(page_title="SUI Scraper V4", layout="wide")
st.title("🔹 SUI Wallet Scraper (Final V4)")

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
    # IMPORTANT: 4K Resolution prevents columns (like Time) from being hidden
    options.add_argument('--window-size=2560,1440')
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
        
        # --- 1. Get Balance (Restored & Fixed) ---
        st.write("Fetching Balance...")
        time.sleep(5) # Allow React to render
        
        balance_val = "Not Found"
        try:
            # Strategy: Find "SUI Balance" label, then find the specific 'div' with class 'value' nearby
            # This is specific enough to work, but broad enough to handle layout shifts
            balance_container = driver.find_element(By.XPATH, "//*[contains(text(), 'SUI Balance')]/ancestor::div[2]")
            balance_text = balance_container.text
            
            # Regex to pull number from that specific container text
            match = re.search(r"(\d{1,3}(?:,\d{3})*\.\d+)", balance_text)
            if match:
                balance_val = match.group(1)
            else:
                # Backup: Look for the specific value class often used by Suiscan
                val_el = driver.find_element(By.XPATH, "//*[contains(text(), 'SUI Balance')]/..//div[contains(@class, 'value')]")
                balance_val = val_el.text
                
            st.metric("SUI Balance", balance_val)
        except Exception as e:
            st.warning(f"Could not read balance (showing {balance_val}). Error: {str(e)}")

        # --- 2. Switch to Activity ---
        try:
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(3)
        except:
            st.write("Activity tab might already be active.")

        # --- 3. Scrape Loop ---
        progress = st.progress(0)
        
        for i in range(max_pages):
            st.write(f"📄 Scraping Page {i+1}...")
            
            # Scroll to bottom to ensure 'Next' arrow is in view
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Find rows
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            
            if not rows:
                st.warning("No transactions found on this page.")
                break
            
            page_count = 0
            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")

                    # Robust Timestamp: Grab text of the WHOLE ROW and scan for date
                    # This works even if the specific 'Time' column div is hidden or nested deeply
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_full_text = row_container.text
                    
                    # Regex for 'YYYY-MM-DD HH:MM:SS'
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_full_text)
                    
                    if date_match:
                        timestamp = date_match.group(1)
                    else:
                        timestamp = "N/A" # If truly missing, mark N/A

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

            # --- Pagination (Javascript Force Click) ---
            if i < max_pages - 1:
                try:
                    # Look for ANY button that contains the Right Arrow SVG
                    # This is the most robust way to find the 'Next' button
                    next_arrow_btn = driver.find_elements(By.XPATH, "//button[descendant::*[name()='svg' and (contains(@data-icon, 'right') or contains(@class, 'chevron-right'))]]")
                    
                    clicked = False
                    if next_arrow_btn:
                        # The last one is usually 'Next' (First one might be 'Last Page' or 'Prev')
                        target_btn = next_arrow_btn[-1]
                        
                        if target_btn.is_enabled():
                            driver.execute_script("arguments[0].click();", target_btn)
                            clicked = True
                            time.sleep(4)
                    
                    if not clicked:
                        st.warning("Next button not found or disabled (End of list).")
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
