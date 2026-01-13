import streamlit as st
import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

# --- CONFIGURATION ---
st.set_page_config(page_title="SUI Scraper Final", layout="wide")
st.title("🔹 SUI Wallet Scraper (Visual Fix)")

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
    # Force a very wide desktop view to prevent "Mobile Layout"
    options.add_argument('--window-size=2560,1440')
    # Use a standard Desktop User-Agent
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
        
        # --- 1. FETCH BALANCE (Fuzzy Search) ---
        st.write("Fetching Balance...")
        time.sleep(5) 
        
        balance_found = "Not Found"
        try:
            # Get all text from the page
            page_text = driver.find_element(By.TAG_NAME, "body").text
            
            # Regex: Look for 'Balance' followed by any characters/newlines, then a number
            # This handles cases where 'SUI' is an icon and not text
            match = re.search(r"Balance\s*\n\s*([0-9,]+\.[0-9]+)", page_text)
            
            if match:
                balance_found = match.group(1)
            else:
                # Fallback: Look for the specific number format if label is missing
                # Matches 91.779699862 exactly
                match_num = re.search(r"(\d{2,}\.\d{5,})", page_text)
                if match_num:
                    balance_found = match_num.group(1)
                    
            st.metric("SUI Balance", balance_found)
        except Exception as e:
            st.warning(f"Balance warning: {e}")

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
            
            # Scroll heavily to ensure everything renders
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
                    
                    # --- TIMESTAMP FIX (Age vs Date) ---
                    # We grab the full row text and look for EITHER a date OR an 'Age' (e.g., 19h 55m)
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    row_text = row_container.text
                    
                    # 1. Try finding absolute date
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                    if date_match:
                        timestamp = date_match.group(1)
                    else:
                        # 2. If no date, find the 'Age' column (usually ends with 'm', 'h', 'd' or 'ago')
                        # We try to read the 'title' attribute which often hides the real date
                        try:
                            # Look for any div/span with a title attribute containing "202" (e.g., 2026)
                            hidden_date_el = row_container.find_element(By.XPATH, ".//*[contains(@title, '202')]")
                            timestamp = hidden_date_el.get_attribute("title")
                        except:
                            # 3. Final Fallback: Scrape the 'Age' text (e.g., "19h 55m")
                            # We look for the last text element in the row
                            try:
                                timestamp = row_container.find_element(By.XPATH, ".//div[last()]").text
                            except:
                                timestamp = "N/A"

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

            # --- PAGINATION FIX (Location Based) ---
            if page_num < max_pages - 1:
                try:
                    # Finds the SVG icon for "Right"
                    next_arrow = driver.find_elements(By.XPATH, "//*[name()='svg' and (contains(@class, 'chevron-right') or contains(@class, 'lucide-chevron-right'))]")
                    
                    if next_arrow:
                        # The 'Next' button is almost always the LAST arrow icon on the page
                        target_arrow = next_arrow[-1]
                        
                        # Click the PARENT button of the svg
                        parent_btn = target_arrow.find_element(By.XPATH, "./ancestor::button | ./ancestor::div[@role='button']")
                        
                        # Scroll into view (CRITICAL FIX)
                        driver.execute_script("arguments[0].scrollIntoView(true);", parent_btn)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", parent_btn)
                        
                        time.sleep(4) # Wait for load
                    else:
                        st.warning("Next button arrow not found.")
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
