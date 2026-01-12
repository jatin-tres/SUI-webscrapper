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
st.title("🔹 SUI Wallet Scraper (Final V2)")

# --- Sidebar ---
with st.sidebar:
    st.header("Settings")
    wallet_address = st.text_input("Wallet Address", value="0xa36a0602be0fcbc59f7864c76238e5e502a1e13150090aab3c2063d34dde1d8a")
    max_pages = st.number_input("Max Pages", 1, 20, 3)
    start_btn = st.button("🚀 Start Scraping", type="primary")

# --- Cloud-Compatible Driver ---
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
        wait = WebDriverWait(driver, 20)
        
        # --- 1. SUI Balance (Display Only) ---
        st.write("Fetching Balance...")
        time.sleep(5) 
        
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.split('\n')
            balance_val = "Not Found"
            
            # Simple line scanner
            for index, line in enumerate(body_text):
                if "Balance" in line and "SUI" in line:
                    if index + 1 < len(body_text):
                        next_line = body_text[index + 1]
                        if any(char.isdigit() for char in next_line):
                            balance_val = next_line
                            break
            # Fallback scanner
            if balance_val == "Not Found":
                 for index, line in enumerate(body_text):
                    if line.strip() == "Balance":
                        if index + 1 < len(body_text):
                            balance_val = body_text[index+1]
                            break
            st.metric("SUI Balance", balance_val)
        except:
            st.warning("Could not read balance, proceeding to transactions...")

        # --- 2. Switch to Activity ---
        try:
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(3)
        except:
            st.write("Activity tab might already be active.")

        # --- 3. Scrape Table ---
        progress = st.progress(0)
        
        for i in range(max_pages):
            st.write(f"📄 Scraping Page {i+1}...")
            
            # Scroll down to make sure 'Next' button loads
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Find all Rows (we look for the rows that contain the Tx Link)
            # This 'row' element allows us to grab the text for that entire line
            rows_elements = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]/ancestor::div[contains(@class, 'row') or contains(@class, 'tr') or ./parent::td/parent::tr]")
            
            # Fallback: if complex row xpath fails, just find the links and assume standard row
            if not rows_elements:
                 rows_elements = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]/../../..")

            if not rows_elements:
                st.warning("No transactions found on this page.")
                break
            
            page_count = 0
            for row in rows_elements:
                try:
                    row_text = row.text
                    
                    # 1. Get Hash/Link (Find the 'a' tag inside this row)
                    link_el = row.find_element(By.XPATH, ".//a[contains(@href, '/tx/')]")
                    tx_hash = link_el.text
                    tx_url = link_el.get_attribute("href")

                    # 2. Get Time using REGEX (Fail-safe)
                    # Looks for pattern: "YYYY-MM-DD HH:MM:SS"
                    # Example: 2026-01-11 23:13:12
                    time_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", row_text)
                    
                    if time_match:
                        timestamp = time_match.group(1)
                    else:
                        # Fallback: Just take the last piece of text in the row
                        timestamp = row_text.split('\n')[-1]

                    if tx_hash:
                        all_data.append({
                            "Transaction Hash": tx_hash,
                            "Timestamp": timestamp,
                            "Link": tx_url
                        })
                        page_count += 1
                except:
                    continue
            
            st.success(f"Collected {page_count} items from Page {i+1}")

            # --- Pagination (Next Button Fix) ---
            if i < max_pages - 1:
                try:
                    # Look specifically for the Right Arrow icon (SVG)
                    # This finds the SVG, then goes up to the clickable parent (button or div)
                    next_btn = driver.find_element(By.XPATH, "//*[name()='svg' and contains(@class, 'lucide-chevron-right') or contains(@class, 'fa-chevron-right') or @data-icon='chevron-right'] | //button[contains(., 'Next')] | //button[./*[name()='svg']][last()]")
                    
                    # If the button is disabled, we stop
                    if "disabled" in next_btn.get_attribute("class") or next_btn.get_attribute("disabled"):
                        st.write("Reached last page.")
                        break

                    driver.execute_script("arguments[0].click();", next_btn)
                    time.sleep(4) # Wait for reload
                except:
                    # Retry: Try clicking the "Next" arrow by just finding the last arrow on screen
                    try:
                        arrows = driver.find_elements(By.CSS_SELECTOR, "button svg, div[role='button'] svg")
                        if arrows:
                            driver.execute_script("arguments[0].parentElement.click();", arrows[-1])
                            time.sleep(4)
                        else:
                            st.write("No next button found.")
                            break
                    except:
                        st.write("Pagination failed.")
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
