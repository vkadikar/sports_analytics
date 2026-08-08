"""
Session management and automated authentication helpers for Fantrax API.
"""

import os
import pickle
import time
from typing import List, Dict, Optional
import requests
from requests import Session


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)


class FantraxSessionManager:
    """Manages HTTP session state, headers, and automated cookie authentication for Fantrax API requests."""

    def __init__(
        self,
        cookie_path: Optional[str] = "fantraxloggedin.cookie",
        username: Optional[str] = None,
        password: Optional[str] = None,
        session: Optional[Session] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        auto_login: bool = False,
    ):
        """Initialize FantraxSessionManager.

        Args:
            cookie_path: Path to pickle file containing serialized browser cookies.
            username: Optional Fantrax account username/email.
            password: Optional Fantrax account password.
            session: Optional existing requests.Session instance.
            user_agent: Custom User-Agent header string.
            auto_login: If True, attempts automated login if cookies are missing/expired and credentials exist.
        """
        # Resolve cookie_path to absolute path across workspace root if needed
        resolved_cookie_path = cookie_path or "fantraxloggedin.cookie"
        if not os.path.isabs(resolved_cookie_path):
            workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            possible_paths = [
                os.path.abspath(resolved_cookie_path),
                os.path.join(workspace_root, resolved_cookie_path),
                os.path.join(workspace_root, "soccer", resolved_cookie_path),
            ]
            for p in possible_paths:
                if os.path.exists(p):
                    resolved_cookie_path = p
                    break
            else:
                resolved_cookie_path = os.path.join(workspace_root, resolved_cookie_path)

        self.cookie_path = resolved_cookie_path
        self.username = username or os.getenv("FANTRAX_USERNAME") or os.getenv("FANTRAX_EMAIL")
        self.password = password or os.getenv("FANTRAX_PASSWORD")
        self.session = session or requests.Session()
        self.auto_login = auto_login
        self.user_agent = user_agent
        self.session.headers.update({"User-Agent": self.user_agent})

        # Always load existing cookies from file if present
        self.load_cookies_from_file(self.cookie_path)

    def load_cookies_from_file(self, cookie_path: Optional[str] = None) -> int:
        """Loads serialized cookies from a pickle file into the requests Session.

        Args:
            cookie_path: Optional path to cookie pickle file.

        Returns:
            Number of cookies loaded.
        """
        target_path = cookie_path or self.cookie_path
        if not os.path.exists(target_path):
            return 0

        try:
            with open(target_path, "rb") as f:
                cookies: List[Dict] = pickle.load(f)
        except Exception:
            return 0

        count = 0
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value:
                self.session.cookies.set(name, value)
                count += 1

        if count > 0:
            self.session.cookies.set("fantraxloggedin", "true", domain=".fantrax.com")

        return count

    def save_cookies_to_file(self, cookie_path: Optional[str] = None) -> None:
        """Saves current session cookies to a pickle file.

        Args:
            cookie_path: Output file path.
        """
        target_path = cookie_path or self.cookie_path
        cookies = [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
            for c in self.session.cookies
        ]
        with open(target_path, "wb") as f:
            pickle.dump(cookies, f)

    def login_with_credentials(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        cookie_output_path: Optional[str] = None,
        headless: bool = True,
        timeout: int = 20,
    ) -> bool:
        """Automates headless browser login via Selenium using email & password.

        Args:
            username: Fantrax account email/username.
            password: Fantrax account password.
            cookie_output_path: Path to save extracted cookie pickle file.
            headless: Whether to run Chrome in headless mode.
            timeout: Maximum seconds to wait for login elements and redirect.

        Returns:
            True if login succeeded and cookies were saved; False otherwise.
        """
        user = username or self.username
        pwd = password or self.password
        out_path = cookie_output_path or self.cookie_path

        if not user or not pwd:
            raise ValueError(
                "Automated login requires username and password. "
                "Provide them as arguments or set environment variables FANTRAX_USERNAME and FANTRAX_PASSWORD."
            )

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            raise ImportError(
                "Selenium and webdriver_manager are required for automated login. "
                "Please install them via: pip install selenium webdriver-manager"
            )

        options = Options()
        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument(f"user-agent={self.user_agent}")

        service = Service(ChromeDriverManager().install())

        with webdriver.Chrome(service=service, options=options) as driver:
            driver.get("https://www.fantrax.com/login")

            # Selector list for Angular / Material UI inputs
            email_selector = "input[name='email'], input#email, input[type='email'], input#mat-input-0, input[type='text']"
            password_selector = "input[name='password'], input#password, input[type='password'], input#mat-input-1"
            button_selector = "button[type='submit'], button.login, button.mat-mdc-unelevated-button"

            # Wait for email input element
            email_input = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, email_selector))
            )
            email_input.clear()
            email_input.send_keys(user)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", email_input)

            # Find and fill password element
            password_input = driver.find_element(By.CSS_SELECTOR, password_selector)
            password_input.clear()
            password_input.send_keys(pwd)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", password_input)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", password_input)

            time.sleep(0.5)
            # Find and click login button
            submit_btn = driver.find_element(By.CSS_SELECTOR, button_selector)
            submit_btn.click()

            # Wait specifically until fantraxloggedin cookie is set by Angular authentication
            start_time = time.time()
            logged_in_cookie = None
            while (time.time() - start_time) < timeout:
                all_cookies = driver.get_cookies()
                for c in all_cookies:
                    if c.get("name") == "fantraxloggedin" and str(c.get("value")).lower() not in ["false", ""]:
                        logged_in_cookie = c
                        break
                if logged_in_cookie:
                    break
                time.sleep(0.5)

            cookies = driver.get_cookies()
            if not logged_in_cookie and headless:
                print("Headless mode did not receive valid login cookie. Retrying with visible browser window...")
                return self.login_with_credentials(
                    username=username,
                    password=password,
                    cookie_output_path=cookie_output_path,
                    headless=False,
                    timeout=timeout,
                )
            elif not logged_in_cookie:
                print("Warning: Automated login completed without receiving a valid fantraxloggedin cookie.")
                return False

            # Save cookies to file
            with open(out_path, "wb") as f:
                pickle.dump(cookies, f)

        # Load fresh cookies into session
        self.load_cookies_from_file(out_path)
        return len(cookies) > 0

    def auto_authenticate(self) -> bool:
        """Attempts to load cookies from file, or performs automated login if credentials are set.

        Returns:
            True if session contains cookies; False otherwise.
        """
        # Step 1: Try loading existing cookie file
        count = self.load_cookies_from_file(self.cookie_path)
        if count > 0:
            return True

        # Step 2: If cookies missing and credentials available, attempt automated login
        if self.username and self.password:
            try:
                return self.login_with_credentials(
                    username=self.username,
                    password=self.password,
                    cookie_output_path=self.cookie_path,
                )
            except Exception:
                return False

        return False
