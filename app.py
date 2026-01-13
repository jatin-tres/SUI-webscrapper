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
st.set_page_config(page_title="SUI Scraper V5", layout="wide")
st.title("🔹 SUI Wallet Scraper (Deep Selectors)")

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
    options.add_argument('--window-size=2560,1440') # Large width to force columns to show
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
        
        # --- 1. FETCH BALANCE (Text Window Method) ---
        st.write("Fetching Balance...")
        time.sleep(5) 
        
        balance_found = "Not Found"
        try:
            # Get entire page text
            full_text = driver.find_element(By.TAG_NAME, "body").text
            # Find index of "SUI Balance"
            idx = full_text.find("SUI Balance")
            if idx != -1:
                # Look at the next 100 characters after the label
                snippet = full_text[idx:idx+100]
                # Regex to find the first number formatting (e.g., 91.779...)
                match = re.search(r"(\d{1,3}(?:,\d{3})*\.\d+)", snippet)
                if match:
                    balance_found = match.group(1)
            st.metric("SUI Balance", balance_found)
        except Exception as e:
            st.warning(f"Balance error: {e}")

        # --- 2. NAVIGATE TO ACTIVITY ---
        try:
            # Force click the tab using JS
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(3)
        except:
            st.write("Activity tab might already be active.")

        # --- 3. SCRAPE LOOP ---
        progress = st.progress(0)
        
        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Scroll down to ensure table and pagination render
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Find Rows (Standard Anchor Strategy)
            rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            
            if not rows:
                st.warning("No transactions found. (Table might be empty or loading)")
                break
                
            page_data = []
            for row_link in rows:
                try:
                    tx_hash = row_link.text
                    tx_url = row_link.get_attribute("href")
                    
                    # --- TIMESTAMP FIX ---
                    # 1. Try finding the sibling div that contains the date
                    # We go up to the row, then find the div with class 'time' or simply the last div
                    timestamp = "N/A"
                    try:
                        # Locate the row container
                        row_container = row_link.find_element(By.XPATH, "./ancestor::div[contains(@class, 'row') or @role='row'] | ./ancestor::tr")
                        
                        # Grab ALL text in the row to regex search it (Most robust)
                        row_full_text = row_container.text
                        
                        # Regex for standard date YYYY-MM-DD
                        date_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_full_text)
                        if date_match:
                            timestamp = date_match.group(1)
                        else:
                            # Fallback: Look for a tooltip/title attribute in the time column
                            # Suiscan often puts the full date in title="2026-01-11..."
                            time_el = row_container.find_element(By.XPATH, ".//div[contains(@class, 'time') or contains(@class, 'date')]//span | .//div[contains(@title, '-')]")
                            title_val = time_el.get_attribute("title")
                            if title_val and "20" in title_val:
                                timestamp = title_val
                    except:
                        pass # Keep N/A if failed

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

            # --- PAGINATION FIX (Deep Selector) ---
            if page_num < max_pages - 1:
                try:
                    # Find ANY element that acts as a 'Next' button
                    # We look for the Right Arrow SVG specifically
                    # Selector: Find an SVG with 'right' in its name/class, inside a button or clickable div
                    next_arrow = driver.find_elements(By.XPATH, "//*[name()='svg' and (contains(@class, 'chevron-right') or contains(@class, 'lucide-chevron-right'))]/ancestor::button | //button[contains(@class, 'pagination-next')]")
                    
                    clicked = False
                    if next_arrow:
                        # The last one found is usually the active "Next" button
                        target = next_arrow[-1]
                        if target.is_enabled():
                            driver.execute_script("arguments[0].click();", target)
                            clicked = True
                            time.sleep(4) # Wait for table reload
                    
                    if not clicked:
                        # Fallback: Try generic pagination button logic
                        all_buttons = driver.find_elements(By.XPATH, "//div[contains(@class, 'pagination')]//button")
                        if all_buttons:
                            driver.execute_script("arguments[0].click();", all_buttons[-1])
                            time.sleep(4)
                        else:
                            st.warning("Next button not found (End of list).")
                            break
                except Exception as e:
                    st.write(f"Pagination error: {e}")
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
