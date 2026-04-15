from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
)
from automation.modules.tempmail import close_consent_popups
import time
from dataclasses import dataclass
from automation.modules.regenerate_guard import load_guard_script
from pathlib import Path


@dataclass
class ChatResult:
    chat_url: str
    response_html: str
    response_text: str


def wait_and_click(driver, css_selector: str, timeout: int = 15, description: str = ""):
    wait = WebDriverWait(driver, timeout)
    try:
        el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector)))
        try:
            el.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", el)
        print(f"[*] Clicked {description} successfully.")
        return True
    except TimeoutException:
        print(
            f"[!] Timeout waiting for {description} ('{css_selector}') to become clickable."
        )
        return False


def ensure_agent_mode(driver, js_dir: Path):
    driver.set_page_load_timeout(45)
    for attempt in range(3):
        try:
            driver.get("https://chat.z.ai/")
            if (
                "ERR_SOCKS_CONNECTION_FAILED" in driver.page_source
                or "ERR_PROXY_CONNECTION_FAILED" in driver.page_source
                or "ERR_CONNECTION_CLOSED" in driver.page_source
            ):
                raise Exception("Proxy/Network error page displayed")
            break
        except TimeoutException:
            print(
                "[!] Page load timed out. Proceeding anyway since the UI might be partially rendered..."
            )
            break
        except Exception as e:
            if attempt == 2:
                print(f"[!] Error loading chat.z.ai after 3 attempts: {e}")
                return False
            print(f"[!] Failed to load chat.z.ai, retrying ({attempt + 1}/3)...")
            time.sleep(2)

    wait = WebDriverWait(driver, 20)

    try:
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea#chat-input"))
        )
    except TimeoutException:
        print("[!] Timeout waiting for chat input. Proceeding...")
    except Exception as e:
        print(f"[!] Error waiting for chat input: {e}")
        return False

    close_consent_popups(driver)

    # Try closing any onboarding modals
    try:
        modals = driver.find_elements(
            By.CSS_SELECTOR,
            "button.dismiss-button, .modal-close, button[aria-label='Close'], button[class*='close']",
        )
        for m in modals:
            if m.is_displayed():
                driver.execute_script("arguments[0].click();", m)
                time.sleep(0.5)
    except:
        pass

    print("[*] Switching to Agent mode...")
    agent_btn = driver.execute_script("""
        return document.querySelector('#sidebar button svg path[d^="M4.65005 5.02227"]')?.closest('button');
    """)
    if agent_btn:
        try:
            wait.until(EC.element_to_be_clickable(agent_btn))
            driver.execute_script("arguments[0].click();", agent_btn)
            print("[*] Clicked Agent mode button.")
        except Exception as e:
            print(f"[!] Failed to click agent button: {e}")
    else:
        print("[!] Agent button not found via SVG path.")

    time.sleep(3)

    print("[*] Selecting GLM-5 model...")
    trigger_found = wait_and_click(
        driver,
        "#model-selector-glm-5-button, .modelSelectorButton, button[data-testid*='model-selector']",
        timeout=10,
        description="Model Dropdown Trigger",
    )

    if trigger_found:
        time.sleep(1)
        wait_and_click(
            driver,
            "button[data-value='glm-5'], li[data-value='glm-5']",
            timeout=10,
            description="GLM-5 Option",
        )

    time.sleep(2)
    guard_script = load_guard_script(js_dir)
    driver.execute_script(guard_script)


def start_prompt(driver, prompt_text: str, wait_seconds: int = 5) -> bool:
    print("[*] Waiting for chat input to be interactable...")
    wait = WebDriverWait(driver, 30)

    try:
        chat_input = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "textarea#chat-input"))
        )
    except TimeoutException:
        print("[!] Timeout waiting for textarea#chat-input. Taking screenshot...")
        driver.save_screenshot(
            "/home/alan/zai-automation/artifacts/screenshots/chat_input_timeout.png"
        )
        return False

    # Inject text via JS to avoid slow typing rendering issues
    driver.execute_script(
        """
        var input = arguments[0], text = arguments[1];
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        nativeInputValueSetter.call(input, text);
        var ev = new Event('input', { bubbles: true });
        input.dispatchEvent(ev);
    """,
        chat_input,
        prompt_text,
    )

    time.sleep(1)

    try:
        chat_input.send_keys(Keys.RETURN)
    except Exception as e:
        print(f"[!] Standard send_keys(RETURN) failed: {e}. Attempting fallback.")
        try:
            # First fallback: explicitly click the send button if it exists
            send_btn = driver.find_element(
                By.CSS_SELECTOR,
                "button[aria-label*='end'], #send-message-button, button[type='submit']",
            )
            driver.execute_script("arguments[0].click();", send_btn)
            print("[*] Clicked the send button via JS fallback.")
        except Exception as btn_e:
            print(f"[!] Fallback button click failed: {btn_e}")
            # Last resort: dispatch JS KeyboardEvent
            driver.execute_script(
                """
                var input = arguments[0];
                var kent = new KeyboardEvent('keydown', {
                    bubbles: true, cancelable: true, keyCode: 13
                });
                input.dispatchEvent(kent);
                """
            )
            print("[*] Dispatched Enter key event via JS.")

    time.sleep(wait_seconds)
    return True


def release_sandboxes(driver):
    try:
        print("[*] Checking for stuck sandboxes...")
        # 1. Click User Menu
        user_menu = driver.find_elements(
            By.CSS_SELECTOR, "button[aria-label='User Menu']"
        )
        if not user_menu:
            print("[*] User menu not found, skipping sandbox release.")
            return False

        driver.execute_script("arguments[0].click();", user_menu[0])
        time.sleep(1)

        # 2. Click Settings
        settings_btn = driver.find_elements(
            By.XPATH, "//button[.//div[contains(text(), 'Settings')]]"
        )
        if settings_btn:
            driver.execute_script("arguments[0].click();", settings_btn[0])
        time.sleep(1)

        # 3. Click Sandbox tab
        sandbox_tab = driver.find_elements(
            By.XPATH, "//button[.//div[contains(text(), 'Sandbox')]]"
        )
        if sandbox_tab:
            driver.execute_script("arguments[0].click();", sandbox_tab[0])
        time.sleep(2)

        # 4. Release sandboxes with TTL "-"
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        released_any = False
        for row in rows:
            tds = row.find_elements(By.CSS_SELECTOR, "td")
            if len(tds) >= 3:
                ttl_text = tds[2].text.strip()
                if "-" in ttl_text:
                    release_btns = row.find_elements(
                        By.XPATH, ".//button[contains(text(), 'Release sandbox')]"
                    )
                    if release_btns:
                        print("[*] Found sandbox with TTL '-'. Releasing...")
                        driver.execute_script("arguments[0].click();", release_btns[0])
                        time.sleep(1)
                        released_any = True

        # 5. Close settings (press Escape or click outside)
        driver.find_element(By.CSS_SELECTOR, "body").send_keys(Keys.ESCAPE)
        time.sleep(1)

        # Return true if we released anything so we can retry
        return released_any

    except Exception as e:
        print(f"[!] Error releasing sandboxes: {e}")
        return False


def click_regenerate(driver):
    try:
        regen_btn = driver.find_element(
            By.CSS_SELECTOR,
            "button[aria-label*='egenerate'], .regenerate-button, button.regenerate",
        )
        if regen_btn.is_displayed() and regen_btn.is_enabled():
            print("[*] Found Regenerate button. Clicking it to heal generation...")
            driver.execute_script("arguments[0].click();", regen_btn)
            time.sleep(2)
            return True
    except Exception as e:
        if (
            "invalid session id" in str(e).lower()
            or "tab crashed" in str(e).lower()
            or "no such window" in str(e).lower()
        ):
            raise e

    # Try finding an error retry button
    try:
        retry_btn = driver.find_element(
            By.XPATH,
            "//button[contains(text(), 'Retry') or contains(text(), 'Try again')]",
        )
        if retry_btn.is_displayed() and retry_btn.is_enabled():
            print("[*] Found Retry button. Clicking it to heal generation...")
            driver.execute_script("arguments[0].click();", retry_btn)
            time.sleep(2)
            return True
    except:
        pass

    return False


def handle_sandbox_popup(driver) -> bool:
    """Check for the Limit Sandbox Concurrency popup and release sandboxes with TTL '-'"""
    try:
        # Check if the popup is present
        popups = driver.find_elements(
            By.XPATH, "//div[contains(text(), 'Limit Sandbox Concurrency')]"
        )
        if not popups:
            return False

        print("[*] Detected 'Limit Sandbox Concurrency' popup!")
        time.sleep(1)

        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        released_any = False

        for row in rows:
            tds = row.find_elements(By.CSS_SELECTOR, "td")
            if len(tds) >= 4:
                last_conv = tds[1].text.strip()
                ttl = tds[2].text.strip()

                if ttl == "-" or last_conv == "-":
                    try:
                        btn = tds[3].find_element(By.TAG_NAME, "button")
                        driver.execute_script("arguments[0].click();", btn)
                        print(
                            f"[*] Released sandbox with TTL: {ttl}, Last Conv: {last_conv}"
                        )
                        time.sleep(1)
                        released_any = True
                    except Exception as e:
                        print(f"[!] Failed to click release button on row: {e}")

        # Close the popup using the close button in the header
        try:
            close_btn = driver.find_element(
                By.XPATH,
                "//div[contains(text(), 'Limit Sandbox Concurrency')]/following-sibling::button",
            )
            driver.execute_script("arguments[0].click();", close_btn)
            print("[*] Closed sandbox popup.")
            time.sleep(1)
        except Exception as e:
            print(f"[!] Failed to close popup: {e}")

        return released_any
    except Exception as e:
        print(f"[!] Error handling sandbox popup: {e}")
        return False


def check_generation_status(driver) -> tuple[str, ChatResult | None]:
    try:
        # 0. Check and clear any Limit Sandbox Concurrency popups
        if handle_sandbox_popup(driver):
            # We hit a limit and cleared it. Let the main loop know we hit the sandbox limit so it can retry
            return "SANDBOX_LIMIT", None

        # 1. Check if error/regenerate is visible
        if click_regenerate(driver):
            return "ERROR", None
    except Exception as e:
        if (
            "stale element reference" in str(e).lower()
            or "staleelementreference" in str(e).lower()
        ):
            return "GENERATING", None
        if (
            "invalid session id" in str(e).lower()
            or "tab crashed" in str(e).lower()
            or "no such window" in str(e).lower()
        ):
            raise e
        return "GENERATING", None

    try:
        # 2. Check if the send button is disabled (meaning it's actively generating)
        send_btns = driver.find_elements(
            By.CSS_SELECTOR,
            "button[aria-label*='end'], #send-message-button, button[type='submit']",
        )
        is_generating = False
        if send_btns:
            # If the button has a disabled attribute, it's generating
            btn = send_btns[-1]
            if (
                not btn.is_enabled()
                or btn.get_attribute("disabled") is not None
                or btn.get_attribute("aria-disabled") == "true"
            ):
                is_generating = True

        if is_generating:
            return "GENERATING", None

        # 3. Check if the copy response button is visible (meaning generation finished)
        # Using a simplified selector for the copy button to avoid escaping issues with Tailwind classes
        copy_btns = driver.find_elements(
            By.CSS_SELECTOR,
            "button.copy-response-button, button[class*='copy-response-button']",
        )

        # We also need the response text to check for lalobaya
        containers = driver.find_elements(
            By.CSS_SELECTOR,
            "#response-content-container, .response-content, .markdown-prose",
        )

        response_text = ""
        if containers:
            # Get the text of the last container (the most recent response)
            response_text = containers[-1].text

        # If the copy button is present and the send button is enabled, it's finished!
        if copy_btns and not is_generating:
            return "FINISHED", ChatResult(
                chat_url=driver.current_url,
                response_html=containers[-1].get_attribute("innerHTML")
                if containers
                else "",
                response_text=response_text,
            )

        # 4. Check if the generation failed to even start (Sandbox limit reached)
        if send_btns and send_btns[-1].is_enabled() and not containers:
            return "SANDBOX_LIMIT", None

    except Exception as e:
        if (
            "stale element reference" in str(e).lower()
            or "staleelementreference" in str(e).lower()
        ):
            return "GENERATING", None
        print(f"[!] Error checking status: {e}")

    # 5. Otherwise, still generating
    return "GENERATING", None


def to_preview_url(chat_url: str) -> str:
    marker = "/c/"
    if marker not in chat_url:
        raise ValueError(f"Cannot transform non-chat URL: {chat_url}")
    uuid = chat_url.split(marker, 1)[1].split("?", 1)[0]
    return f"https://preview-chat-{uuid}.space.z.ai/"
