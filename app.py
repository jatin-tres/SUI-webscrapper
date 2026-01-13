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
st.set_page_config(page_title="SUI Scraper V6", layout="wide")
st.title("🔹 SUI Wallet Scraper (Position Fix)")

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
        url = f"https://suiscan.xyz/mainnet/account/{wallet_address}"
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        
        # --- 1. FETCH BALANCE ---
        st.write("Fetching Balance...")
        time.sleep(5) 
        
        balance_found = "Not Found"
        try:
            # Fuzzy Text Search (Works 100% if text exists)
            page_text = driver.find_element(By.TAG_NAME, "body").text
            # Look for "Balance" followed by a number
            match = re.search(r"Balance\s*\n\s*([0-9,]+\.[0-9]+)", page_text)
            if match:
                balance_found = match.group(1)
            else:
                # Fallback: Look for the big number pattern directly
                match_num = re.search(r"(\d{2,}\.\d{8,})", page_text)
                if match_num:
                    balance_found = match_num.group(1)
            st.metric("SUI Balance", balance_found)
        except:
            st.warning("Balance could not be read.")

        # --- 2. NAVIGATE TO ACTIVITY ---
        try:
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(3)
        except:
            st.write("Activity tab might already be active.")

        # --- 3. SCRAPE LOOP ---
        progress = st.progress(0)
        
        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Scroll to absolute bottom to force pagination load
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

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
                    
                    # --- TIMESTAMP FIX (Age Detection) ---
                    # We grab the full row text
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    
                    # 1. Search for strict Date (2026-01-11)
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", row_text)
                    if date_match:
                        # Grab the full date time if possible
                        full_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                        timestamp = full_match.group(1) if full_match else date_match.group(1)
                    else:
                        # 2. Search for "Age" pattern (e.g., 19h 55m, 2d, 5m ago)
                        # Looks for digits followed by 'd', 'h', 'm' or 's'
                        age_match = re.search(r"(\d+[dhms]\s*\d*[dhms]*)", row_text.split('\n')[-1]) # Check last part of text
                        if age_match:
                            timestamp = age_match.group(1)
                        else:
                            # 3. Final Fallback: Just take the last piece of text
                            timestamp = row_text.split('\n')[-1]

                    if tx_hash:
                        page_data.append({
                            "Transaction Hash": tx_hash,
                            "Time/Age": timestamp,
                            "Link": tx_url
                        })
                except:
                    continue
            
            all_data.extend(page_data)
            st.success(f"Collected {len(page_data)} items from Page {page_num + 1}")

            # --- PAGINATION FIX (Last Button Strategy) ---
            if page_num < max_pages - 1:
                try:
                    # Instead of finding the arrow, we find the PAGINATION CONTAINER
                    # and click the LAST button inside it.
                    
                    # 1. Find the pagination footer
                    pagination_container = driver.find_elements(By.XPATH, "//div[contains(@class, 'pagination') or contains(@class, 'footer')]")
                    
                    clicked = False
                    if pagination_container:
                        # Find all buttons inside the footer
                        buttons = pagination_container[-1].find_elements(By.TAG_NAME, "button")
                        if buttons:
                            next_btn = buttons[-1] # The last button is ALWAYS Next
                            if next_btn.is_enabled():
                                driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
                                time.sleep(1)
                                driver.execute_script("arguments[0].click();", next_btn)
                                clicked = True
                                time.sleep(4)
                    
                    # 2. Fallback: Find ALL buttons on page and click the last one with an SVG
                    if not clicked:
                        all_svg_btns = driver.find_elements(By.XPATH, "//button[descendant::*[name()='svg']]")
                        if all_svg_btns:
                            driver.execute_script("arguments[0].click();", all_svg_btns[-1])
                            clicked = True
                            time.sleep(4)

                    if not clicked:
                        st.warning("Could not find Next button.")
                        break
                        
                except Exception as e:
                    st.write(f"Pagination stopped: {e}")
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
