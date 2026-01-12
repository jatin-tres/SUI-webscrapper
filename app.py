import streamlit as st
import pandas as pd
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Page Config ---
st.set_page_config(page_title="SUI Scraper", layout="wide")
st.title("🔹 SUI Wallet Scraper (Cloud Fixed)")

# --- Sidebar ---
with st.sidebar:
    wallet_address = st.text_input("Wallet Address", value="0xa36a0602be0fcbc59f7864c76238e5e502a1e13150090aab3c2063d34dde1d8a")
    max_pages = st.number_input("Max Pages", 1, 10, 3)
    start_btn = st.button("🚀 Start Scraping", type="primary")

# --- Optimized Driver for Streamlit Cloud ---
def get_driver():
    options = Options()
    options.add_argument('--headless=new')  # Newer headless mode (less detectable)
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    # Spoof User-Agent to look like a real Windows PC
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # On Streamlit Cloud (Linux), this finds the system installed chromedriver automatically
    return webdriver.Chrome(options=options)

if start_btn:
    st.info(f"Scanning: {wallet_address}...")
    status = st.empty()
    driver = None
    
    try:
        driver = get_driver()
        url = f"https://suiscan.xyz/mainnet/account/{wallet_address}"
        driver.get(url)
        wait = WebDriverWait(driver, 20)
        
        # --- 1. SUI Balance ---
        status.text("🔍 Looking for Balance...")
        time.sleep(3) # Initial load wait
        
        try:
            # Flexible XPath: Finds "SUI Balance" label, then looks for the number inside the same container
            balance_el = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), 'SUI Balance')]/..//*[contains(@class, 'value') or contains(text(), '.')]")
            ))
            st.metric("SUI Balance", balance_el.text)
        except Exception as e:
            st.error(f"Balance Not Found. (See Debug Screenshot below)")
            driver.save_screenshot("debug_balance.png")
            st.image("debug_balance.png", caption="What the bot sees")

        # --- 2. Switch to Activity ---
        status.text("🖱️ Clicking 'Activity'...")
        try:
            # Try multiple selectors for the Activity tab
            activity_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[text()='Activity'] | //span[text()='Activity']")))
            driver.execute_script("arguments[0].click();", activity_tab) # Force click via JS
            time.sleep(3)
        except:
            st.warning("Could not click Activity tab (might be active already).")

        # --- 3. Scrape Table ---
        all_data = []
        for i in range(max_pages):
            status.text(f"📄 Scraping Page {i+1}...")
            time.sleep(2)
            
            # Grab all rows that look like transactions
            rows = driver.find_elements(By.XPATH, "//div[@role='row'] | //tr")
            
            if len(rows) < 2:
                # If no rows, take a debug screenshot
                st.warning("No rows found. Saving debug screenshot...")
                driver.save_screenshot("debug_table.png")
                st.image("debug_table.png", caption="Table View Debug")
                break

            for row in rows:
                try:
                    text = row.text
                    if "Digest" in text or "Time" in text: continue # Skip headers

                    # Extract Hash (Link)
                    try:
                        link_el = row.find_element(By.XPATH, ".//a[contains(@href, '/tx/')]")
                        tx_hash = link_el.text
                        tx_link = link_el.get_attribute("href")
                    except:
                        tx_hash, tx_link = "N/A", ""

                    # Extract Time (Last column)
                    try:
                        time_el = row.find_element(By.XPATH, ".//div[contains(@class, 'time')] | .//td[last()]")
                        timestamp = time_el.text
                    except:
                        timestamp = "N/A"

                    if tx_hash != "N/A":
                        all_data.append({"Hash": tx_hash, "Time": timestamp, "Link": tx_link})
                except:
                    continue
            
            # Click Next Page
            try:
                next_btn = driver.find_element(By.XPATH, "//button[contains(@class, 'next')] | //button[./svg][last()]")
                if not next_btn.is_enabled(): break
                driver.execute_script("arguments[0].click();", next_btn)
            except:
                break

        # --- Results ---
        driver.quit()
        if all_data:
            st.success("Success!")
            df = pd.DataFrame(all_data)
            st.dataframe(df)
            st.download_button("Download CSV", df.to_csv().encode('utf-8'), "sui_data.csv")
        else:
            st.error("No data collected.")

    except Exception as e:
        st.error(f"Critical Error: {e}")
        if driver: driver.quit()
