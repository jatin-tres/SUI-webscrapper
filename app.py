import streamlit as st
import pandas as pd
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- Page Configuration ---
st.set_page_config(page_title="SUI Wallet Scraper", layout="wide")

# --- Title & Description ---
st.title("🔹 SUI Blockchain Wallet Scraper")
st.markdown("""
This app scrapes **SUI Balance** and **Transaction Activity** from [Suiscan](https://suiscan.xyz).
Enter a wallet address below to begin.
""")

# --- Sidebar Inputs ---
with st.sidebar:
    st.header("Settings")
    wallet_address = st.text_input("Wallet Address", value="0xa36a0602be0fcbc59f7864c76238e5e502a1e13150090aab3c2063d34dde1d8a")
    max_pages = st.number_input("Max Pages to Scrape", min_value=1, max_value=50, value=5)
    
    st.write("---")
    start_btn = st.button("🚀 Start Scraping", type="primary")

# --- Helper Function: Setup Selenium ---
def get_driver():
    options = Options()
    options.add_argument('--headless')  # Run in background (no popup window)
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    
    # Auto-install Chrome Driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# --- Main Logic ---
if start_btn:
    if not wallet_address:
        st.error("Please enter a wallet address.")
    else:
        st.info(f"Initiating scraper for: `{wallet_address}`")
        
        # Placeholders for live updates
        status_text = st.empty()
        balance_metric = st.empty()
        progress_bar = st.progress(0)
        dataframe_placeholder = st.empty()
        
        driver = get_driver()
        all_data = []
        
        try:
            # 1. Navigate to Wallet
            url = f"https://suiscan.xyz/mainnet/account/{wallet_address}"
            status_text.text("Navigating to Suiscan...")
            driver.get(url)
            wait = WebDriverWait(driver, 20)

            # 2. Get Balance
            status_text.text("Fetching Wallet Balance...")
            try:
                # Robust XPath to find the number associated with 'SUI Balance'
                balance_el = wait.until(EC.visibility_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'SUI Balance')]/ancestor::div[1]//div[contains(@class, 'value') or contains(text(), '.')]")
                ))
                balance_val = balance_el.text
                balance_metric.metric(label="SUI Balance", value=balance_val)
            except:
                balance_val = "N/A"
                balance_metric.metric(label="SUI Balance", value="Not Found")

            # 3. Go to Activity Tab
            status_text.text("Switching to 'Activity' tab...")
            try:
                activity_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Activity')]")))
                activity_tab.click()
                time.sleep(2) # Animation wait
            except:
                st.warning("Could not click 'Activity' tab. Might already be active.")

            # 4. Filter 'All'
            try:
                all_filter = driver.find_element(By.XPATH, "//button[contains(text(), 'All')]")
                all_filter.click()
                time.sleep(1)
            except:
                pass # Usually default is 'All'

            # 5. Loop Pages
            page_count = 0
            while page_count < max_pages:
                status_text.text(f"Scraping Page {page_count + 1} of {max_pages}...")
                
                # Update progress bar
                progress_bar.progress((page_count + 1) / max_pages)

                # Wait for rows
                time.sleep(3) 
                rows = driver.find_elements(By.XPATH, "//tbody/tr | //div[@role='row']")

                if not rows:
                    st.warning("No rows found on this page.")
                    break

                # Extract Row Data
                page_data = []
                for row in rows:
                    try:
                        # Tx Hash
                        hash_el = row.find_element(By.XPATH, ".//a[contains(@href, '/tx/') or contains(@class, 'hash')]")
                        tx_hash = hash_el.text
                        tx_link = hash_el.get_attribute("href")
                        
                        # Timestamp (Last column)
                        time_el = row.find_element(By.XPATH, ".//td[last()] | .//div[last()]")
                        timestamp = time_el.text

                        if tx_hash:
                            all_data.append({
                                "Wallet Balance": balance_val,
                                "Transaction Hash": tx_hash,
                                "Timestamp": timestamp,
                                "Link": tx_link
                            })
                    except:
                        continue
                
                # Update the live table view
                if all_data:
                    df = pd.DataFrame(all_data)
                    dataframe_placeholder.dataframe(df, height=300)

                # Pagination: Next Button
                try:
                    # Look for the 'Next' arrow button (usually the last button in pagination div)
                    next_btns = driver.find_elements(By.XPATH, "//button[contains(@class, 'pagination') or .//svg]")
                    if not next_btns:
                        break # No pagination found
                    
                    next_btn = next_btns[-1] # Assume last button is 'Next'

                    if not next_btn.is_enabled():
                        break # Button disabled (End of list)
                    
                    next_btn.click()
                    page_count += 1
                    time.sleep(2)
                except:
                    status_text.text("End of pages reached.")
                    break

            status_text.text("✅ Scraping Complete!")
            progress_bar.progress(100)

        except Exception as e:
            st.error(f"An error occurred: {e}")
        
        finally:
            driver.quit()

        # --- Download Section ---
        if all_data:
            df_final = pd.DataFrame(all_data)
            st.success(f"Successfully scraped {len(df_final)} transactions.")
            
            csv = df_final.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Data as CSV",
                data=csv,
                file_name=f"sui_activity_{wallet_address[:6]}.csv",
                mime="text/csv",
            )
        else:
            st.warning("No transaction data was found.")
