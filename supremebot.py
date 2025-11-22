import requests
import json
import time
import random
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

class SupremeBot:
    def __init__(self, config_file='config.json'):
        """Initialize the Supreme checkout bot with configuration"""
        self.base_url = "https://www.supremenewyork.com"
        self.shop_path = "/shop/all/jackets"
        self.checkout_path = "/checkout"
        
        # Setup logging first to avoid AttributeError
        self.setup_logging()
        
        # Load configuration
        self.config = self.load_config(config_file)
        
        # Setup web driver
        self.setup_driver()
        
    def load_config(self, config_file):
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                self.log_message(f"Configuration loaded from {config_file}")
                return config
        except FileNotFoundError:
            print(f"Config file {config_file} not found. Creating a default config.")
            default_config = {
                "target_items": [
                    {
                        "keywords": ["Faux", "Fur", "Jacket"],
                        "color": "Red",
                        "size": "Medium"
                    }
                ],
                "billing_info": {
                    "name": "Enter Name",
                    "email": "enter email",
                    "tel": "Enter Phone Number",
                    "address": "Enter address",
                    "apt": "Enter Apt/Suite",
                    "zip": "Enter Zipcode",
                    "city": "Enter City",
                    "state": "Enter State",
                    "country": "USA",
                    "card_type": "visa",
                    "card_number": "4111111111111111",
                    "exp_month": "01",
                    "exp_year": "2026",
                    "cvv": "123"
                },
                "settings": {
                    "refresh_delay": 1.0,
                    "checkout_delay": 0.5,
                    "random_delay_range": [0.2, 0.7],
                    "auto_checkout": True,
                    "headless": False,
                    "proxies": []
                }
            }
            
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=4)
            
            return default_config
    
    def setup_driver(self):
        """Setup the Chrome WebDriver with appropriate options"""
        chrome_options = Options()
        if self.config["settings"].get("headless", False):
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        # Set user agent to look like a regular macOS user
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Using webdriver_manager to handle ChromeDriver installation
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        
        # Modify navigator.webdriver flag to prevent detection
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def setup_logging(self):
        """Setup logging for bot operations"""
        self.log_file = f"supreme_bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.log_message("Supreme Checkout Bot Started")
        
    def log_message(self, message):
        """Log a message with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        
        with open(self.log_file, 'a') as f:
            f.write(log_entry + "\n")
    
    def add_random_delay(self):
        """Add a random delay to mimic human behavior"""
        delay_range = self.config["settings"].get("random_delay_range", [0.2, 0.7])
        delay = random.uniform(delay_range[0], delay_range[1])
        time.sleep(delay)
        time.sleep(random.uniform(2, 5))
        
    def navigate_to_shop(self):
        """Navigate to the shop page"""
        self.log_message("Navigating to Supreme shop")
        self.driver.get(self.base_url + self.shop_path)
        self.add_random_delay()
    
    def search_for_item(self, keywords, color):
        """Search for an item based on keywords and color"""
        self.log_message(f"Searching for item with keywords: {keywords}, color: {color}")
        
        # Wait for items to load
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "inner-article"))
            )
        except TimeoutException:
            self.log_message("Timeout waiting for items to load")
            return False
        
        # Find all items
        items = self.driver.find_elements(By.CLASS_NAME, "inner-article")
        
        for item in items:
            try:
                item_name = item.find_element(By.CLASS_NAME, "name").text
                item_color = item.find_element(By.CLASS_NAME, "style").text
                self.log_message(f"Found item: {item_name}, Color: {item_color}")
                
                # Check if all keywords are in the item name
                if all(keyword.lower() in item_name.lower() for keyword in keywords) and color.lower() in item_color.lower():
                    self.log_message(f"Found matching item: {item_name}, {item_color}")
                    
                    # Click on the item
                    item.click()
                    return True
            except NoSuchElementException:
                continue
        
        self.log_message(f"No item found matching keywords: {keywords}, color: {color}")
        return False
    
    def select_size(self, target_size):
        """Select the desired size if available"""
        self.log_message(f"Selecting size: {target_size}")
        
        try:
            # Wait for size options to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "size"))
            )
            
            # Get the size dropdown
            size_dropdown = self.driver.find_element(By.ID, "size")
            size_options = size_dropdown.find_elements(By.TAG_NAME, "option")
            
            for option in size_options:
                if target_size.lower() in option.text.lower():
                    option.click()
                    self.log_message(f"Selected size: {option.text}")
                    return True
            
            # If specific size not found, select the first available
            if len(size_options) > 1:  # Skip the "Size" placeholder option
                size_options[1].click()
                self.log_message(f"Target size {target_size} not found, selected: {size_options[1].text}")
                return True
                
        except (NoSuchElementException, TimeoutException):
            self.log_message("No size selection available or single size item")
            return True  # Return True for items with no size selection
            
        return False
    
    def add_to_cart(self):
        """Add the selected item to cart"""
        self.log_message("Adding item to cart")
        
        try:
            # Wait for add to cart button
            add_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.NAME, "commit"))
            )
            
            # Click the add to cart button
            add_button.click()
            
            # Wait for cart to update
            self.add_random_delay()
            
            # Check if successfully added to cart
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "in-cart"))
                )
                self.log_message("Item successfully added to cart")
                return True
            except TimeoutException:
                self.log_message("Failed to add item to cart")
                return False
                
        except (NoSuchElementException, TimeoutException):
            self.log_message("Add to cart button not found or not clickable")
            return False
    
    def proceed_to_checkout(self):
        """Navigate to checkout page"""
        self.log_message("Proceeding to checkout")
        
        try:
            # Navigate directly to checkout
            self.driver.get(self.base_url + self.checkout_path)
            
            # Wait for checkout form to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "order_billing_name"))
            )
            
            self.log_message("Successfully navigated to checkout page")
            return True
            
        except TimeoutException:
            self.log_message("Timeout waiting for checkout page")
            return False
    
    def fill_checkout_form(self):
        """Fill in the checkout form with billing and shipping information"""
        self.log_message("Filling checkout form")
        
        billing_info = self.config["billing_info"]
        
        try:
            # Wait for the page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "order_billing_name"))
            )
            
            # Fill in billing and shipping details
            self.driver.find_element(By.ID, "order_billing_name").send_keys(billing_info["name"])
            self.driver.find_element(By.ID, "order_email").send_keys(billing_info["email"])
            self.driver.find_element(By.ID, "order_tel").send_keys(billing_info["tel"])
            self.driver.find_element(By.ID, "bo").send_keys(billing_info["address"])
            self.driver.find_element(By.ID, "oba3").send_keys(billing_info["apt"])
            self.driver.find_element(By.ID, "order_billing_zip").send_keys(billing_info["zip"])
            self.driver.find_element(By.ID, "order_billing_city").send_keys(billing_info["city"])
            
            # Select state
            state_select = self.driver.find_element(By.ID, "order_billing_state")
            for option in state_select.find_elements(By.TAG_NAME, "option"):
                if option.text.strip() == billing_info["state"]:
                    option.click()
                    break
            
            # Credit card details
            self.driver.find_element(By.ID, "rnsnckrn").send_keys(billing_info["card_number"])
            
            # Select expiration month
            exp_month_select = self.driver.find_element(By.ID, "credit_card_month")
            for option in exp_month_select.find_elements(By.TAG_NAME, "option"):
                if option.get_attribute("value") == billing_info["exp_month"]:
                    option.click()
                    break
            
            # Select expiration year
            exp_year_select = self.driver.find_element(By.ID, "credit_card_year")
            for option in exp_year_select.find_elements(By.TAG_NAME, "option"):
                if option.get_attribute("value") == billing_info["exp_year"]:
                    option.click()
                    break
            
            # CVV
            self.driver.find_element(By.ID, "orcer").send_keys(billing_info["cvv"])
            
            # Check terms checkbox
            self.driver.find_element(By.CSS_SELECTOR, "input[type='checkbox'][name='order[terms]']").click()
            
            self.log_message("Checkout form filled successfully")
            return True
            
        except (NoSuchElementException, TimeoutException) as e:
            self.log_message(f"Error filling checkout form: {str(e)}")
            return False
    
    def submit_order(self):
        """Submit the order if auto checkout is enabled"""
        if not self.config["settings"].get("auto_checkout", False):
            self.log_message("Auto checkout disabled, stopping before final submission")
            return True
        
        self.log_message("Submitting order")
        
        try:
            # Find and click the submit button
            submit_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.NAME, "commit"))
            )
            
            # Add checkout delay if specified
            checkout_delay = self.config["settings"].get("checkout_delay", 0)
            if checkout_delay > 0:
                self.log_message(f"Waiting for {checkout_delay} seconds before final checkout")
                time.sleep(checkout_delay)
            
            # Click the submit button
            submit_button.click()
            
            self.log_message("Order submitted successfully")
            return True
            
        except (NoSuchElementException, TimeoutException) as e:
            self.log_message(f"Error submitting order: {str(e)}")
            return False
    
    def run(self):
        """Run the bot to check out items defined in config"""
        self.log_message("Starting Supreme checkout process")
        
        for target_item in self.config["target_items"]:
            keywords = target_item["keywords"]
            color = target_item["color"]
            size = target_item["size"]
            
            self.log_message(f"Targeting item with keywords: {keywords}, color: {color}, size: {size}")
            
            # Navigate to shop
            self.navigate_to_shop()
            
            # Search for the item
            if not self.search_for_item(keywords, color):
                self.log_message(f"Failed to find item with keywords: {keywords}, color: {color}")
                continue
            
            # Select size
            if not self.select_size(size):
                self.log_message(f"Failed to select size: {size}")
                continue
            
            # Add to cart
            if not self.add_to_cart():
                self.log_message("Failed to add item to cart")
                continue
            
            # Proceed to checkout
            if not self.proceed_to_checkout():
                self.log_message("Failed to proceed to checkout")
                continue
            
            # Fill checkout form
            if not self.fill_checkout_form():
                self.log_message("Failed to fill checkout form")
                continue
            
            # Submit order
            if not self.submit_order():
                self.log_message("Failed to submit order")
                continue
            
            # Success!
            self.log_message("Checkout completed successfully!")
            break
        
        # Keep the browser open if not in headless mode
        if not self.config["settings"].get("headless", False):
            input("Press Enter to close the browser...")
        
        # Close the browser
        self.driver.quit()
        self.log_message("Supreme bot finished execution")

# Run the bot if script is executed directly
if __name__ == "__main__":
    print("""
    =========================================
    =      Supreme Checkout Bot for macOS   =
    =========================================
    """)
    
    print("Before running this bot, make sure you have updated the config.json file with:")
    print("1. Target item details (keywords, color, size)")
    print("2. Your billing and shipping information")
    print("3. Bot settings (delays, auto-checkout, etc.)")
    print("\nEnsure you have installed the required dependencies:")
    print("pip install selenium webdriver-manager requests\n")
    
    bot = SupremeBot()
    bot.run()