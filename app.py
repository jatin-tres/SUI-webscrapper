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
st.set_page_config(page_title="SUI Scraper Final", layout="wide")
st.title("🔹 SUI Wallet Scraper (Smart Logic)")

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
    # Force standard Desktop size to keep columns visible
    options.add_argument('--window-size=1920,1080')
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
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            # Look for 91.77... pattern directly if label fails
            match = re.search(r"Balance\s*\n\s*([0-9,]+\.[0-9]+)", body_text)
            balance_found = match.group(1) if match else "Not Found"
            if balance_found == "Not Found":
                 # Fallback regex for the specific number format in your screenshot
                match_strict = re.search(r"(\d{2,}\.\d{5,})", body_text)
                if match_strict: balance_found = match_strict.group(1)
            st.metric("SUI Balance", balance_found)
        except:
            st.warning("Balance not found.")

        # --- 2. NAVIGATE TO ACTIVITY ---
        try:
            act_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
            driver.execute_script("arguments[0].click();", act_tab)
            time.sleep(3)
        except:
            st.write("Activity tab already active.")

        # --- 3. SCRAPE LOOP ---
        progress = st.progress(0)
        
        for page_num in range(max_pages):
            st.write(f"📄 Scraping Page {page_num + 1}...")
            
            # Scroll to ensure elements are interactable
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Get current first item to verify pagination later
            try:
                first_row_check = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")[0].text
            except:
                first_row_check = "none"

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
                    
                    # --- SMART TIMESTAMP FINDER ---
                    # 1. Get the parent row container
                    row_container = row_link.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(@class, 'row')]")
                    
                    # 2. Find specifically the text that looks like time
                    # We look for text matching "202X-" OR "ago" OR "m" / "h" / "d" standing alone
                    # This avoids grabbing the Hash suffix
                    full_row_text = row_container.text
                    
                    # Regex for Date (2026-01-11)
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", full_row_text)
                    
                    # Regex for Age (19h 55m, 2d, etc.) - STRICTER to avoid hash collisions
                    # Looks for a number followed by d/h/m/s, ensuring it's not part of a long string
                    age_match = re.search(r"\b(\d+[dhms]\s*\d*[dhms]*)\b", full_row_text)
                    
                    if date_match:
                        timestamp = date_match.group(1)
                    elif age_match:
                        timestamp = age_match.group(1)
                    else:
                        timestamp = "N/A"

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

            # --- PAGINATION (Multi-Try Strategy) ---
            if page_num < max_pages - 1:
                clicked = False
                try:
                    # Strategy: Find EVERY button that has a 'chevron-right' icon
                    # We iterate and click them until the page data changes
                    candidates = driver.find_elements(By.XPATH, "//button[descendant::*[contains(@class, 'chevron-right') or contains(@class, 'lucide-chevron-right') or contains(@data-icon, 'right')]]")
                    
                    # Also add generic pagination buttons to candidates
                    candidates += driver.find_elements(By.XPATH, "//div[contains(@class, 'pagination')]//button")
                    
                    # Filter for unique, enabled buttons
                    valid_buttons = [btn for btn in candidates if btn.is_enabled()]
                    
                    # Reverse list (Next button is usually last)
                    for btn in reversed(valid_buttons):
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            driver.execute_script("arguments[0].click();", btn)
                            time.sleep(3) # Wait for load
                            
                            # Check if page changed
                            new_rows = driver.find_elements(By.XPATH, "//a[contains(@href, '/tx/')]")
                            if new_rows and new_rows[0].text != first_row_check:
                                clicked = True
                                break # Success!
                        except:
                            continue # Try next button
                    
                    if not clicked:
                        st.warning("Could not find working Next button.")
                        break
                        
                except Exception as e:
                    st.error(f"Pagination failed: {e}")
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
