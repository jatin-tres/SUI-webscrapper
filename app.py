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
st.title("🔹 SUI Wallet Scraper (Final Fix)")

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
        
        # --- 1. SUI Balance (Line-by-Line Method) ---
        # This fixes the "Not Found" and "Too much text" error by reading the visual lines exactly.
        st.write("Fetching Balance...")
        time.sleep(5) 
        
        try:
            # Get all visible text on the page as a list of lines
            body_text = driver.find_element(By.TAG_NAME, "body").text.split('\n')
            balance_val = "Not Found"
            
            # Iterate through lines to find "Balance" and grab the NEXT line
            for index, line in enumerate(body_text):
                if "Balance" in line and "SUI" in line: # Checks for "SUI Balance" or similar
                    # The number is usually on the next line or the same line
                    if index + 1 < len(body_text):
                        next_line = body_text[index + 1]
                        # Check if next line looks like a number (digits and dot)
                        if any(char.isdigit() for char in next_line):
                            balance_val = next_line
                            break
            
            # Fallback: specific to your screenshot structure (SUI -> Balance -> Number)
            if balance_val == "Not Found":
                 for index, line in enumerate(body_text):
                    if line.strip() == "Balance":
                        if index + 1 < len(body_text):
                            balance_val = body_text[index+1]
                            break
                            
            st.metric("SUI Balance", balance_val)
            
        except Exception as e:
            st.error(f"Balance Error: {e}")

        # --- 2. Switch to Activity ---
        try:
            # Force JS Click on Activity Tab
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(3)
        except:
            st.write("Activity tab might already be active.")

        # --- 3. Scrape Table (Pagination Fix) ---
        progress = st.progress(0)
        
        for i in range(max_pages):
            st.write(f"📄 Scraping Page {i+1}...")
            
            # Scroll to bottom to ensure "Next" button is visible (Fixes pagination)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Find Links (Rows)
            tx_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
            
            if not tx_links:
                st.warning("No transactions found on this page.")
                break
            
            # Extract Data
            page_count = 0
            for link in tx_links:
                try:
                    tx_hash = link.text
                    tx_url = link.get_attribute("href")
                    
                    # Find Time: Locate the row container, then find the last text element
                    try:
                        row_time = link.find_element(By.XPATH, "./ancestor::tr//td[last()]").text
                    except:
                        # Fallback for div-based tables
                        row_time = link.find_element(By.XPATH, "./ancestor::div[contains(@class, 'row') or @role='row']//div[last()]").text
                    
                    if tx_hash:
                        all_data.append({
                            "Wallet Balance": balance_val,
                            "Transaction Hash": tx_hash,
                            "Time (Age)": row_time,
                            "Link": tx_url
                        })
                        page_count += 1
                except:
                    continue
            
            st.success(f"Collected {page_count} items from Page {i+1}")

            # --- Pagination Click ---
            if i < max_pages - 1: # Don't click on last loop
                try:
                    # Find all buttons with SVG (arrows) or 'pagination' class
                    # We take the LAST one ([-1]) because the Next arrow is always on the right
                    next_btns = driver.find_elements(By.XPATH, "//button[contains(@class, 'pagination') or .//svg]")
                    
                    if next_btns:
                        next_btn = next_btns[-1] # Robust way to find "Next"
                        
                        if next_btn.is_enabled():
                            # Save current first item to check if page actually changes
                            first_item_old = tx_links[0].text if tx_links else ""
                            
                            driver.execute_script("arguments[0].click();", next_btn)
                            time.sleep(5) # WAIT for table to reload
                            
                            # Optional: Check if page actually changed
                            new_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
                            if new_links and new_links[0].text == first_item_old:
                                st.warning("Page didn't change (End of list or error). Stopping.")
                                break
                        else:
                            st.write("Next button disabled.")
                            break
                    else:
                        st.write("No next button found.")
                        break
                except Exception as e:
                    st.write(f"Pagination stopped: {e}")
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
