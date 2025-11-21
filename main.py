from flask import Flask, render_template, request, jsonify, redirect, url_for
import time
import threading
import uuid
import hashlib
import os
import json
import urllib.parse
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import requests

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-make-it-strong'
app.config['SESSION_TYPE'] = 'filesystem'

WHATSAPP_NUMBER = "9174751272"
ADMIN_UID = "61581843293653"

# Single-user mode (simple)
GLOBAL_USER_ID = "local_user"

# Global automation states
automation_states = {}

class AutomationState:
    def __init__(self):
        self.running = False
        self.message_count = 0
        self.logs = []
        self.message_rotation_index = 0

# Simple in-memory config (no database)
user_config = {
    "chat_id": "",
    "name_prefix": "",
    "delay": 30,
    "cookies": "",
    "messages": ""
}

# Simple in-memory admin thread cache
admin_threads = {}  # {user_id: thread_id}


# =============== HELPERS ===============

def log_message(msg, automation_state=None, user_id=None):
    timestamp = time.strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    
    if automation_state:
        automation_state.logs.append(formatted_msg)
    elif user_id and user_id in automation_states:
        automation_states[user_id].logs.append(formatted_msg)


def find_message_input(driver, process_id, automation_state=None, user_id=None):
    log_message(f'{process_id}: Finding message input...', automation_state, user_id)
    time.sleep(10)
    
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
    except Exception:
        pass
    
    try:
        page_title = driver.title
        page_url = driver.current_url
        log_message(f'{process_id}: Page Title: {page_title}', automation_state, user_id)
        log_message(f'{process_id}: Page URL: {page_url}', automation_state, user_id)
    except Exception as e:
        log_message(f'{process_id}: Could not get page info: {e}', automation_state, user_id)
    
    message_input_selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[aria-label*="message" i][contenteditable="true"]',
        'div[aria-label*="Message" i][contenteditable="true"]',
        'div[contenteditable="true"][spellcheck="true"]',
        '[role="textbox"][contenteditable="true"]',
        'textarea[placeholder*="message" i]',
        'div[aria-placeholder*="message" i]',
        'div[data-placeholder*="message" i]',
        '[contenteditable="true"]',
        'textarea',
        'input[type="text"]'
    ]
    
    log_message(f'{process_id}: Trying {len(message_input_selectors)} selectors...', automation_state, user_id)
    
    for idx, selector in enumerate(message_input_selectors):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            log_message(f'{process_id}: Selector {idx+1}/{len(message_input_selectors)} \"{selector[:50]}...\" found {len(elements)} elements', automation_state, user_id)
            
            for element in elements:
                try:
                    is_editable = driver.execute_script("""
                        return arguments[0].contentEditable === 'true' || 
                               arguments[0].tagName === 'TEXTAREA' || 
                               arguments[0].tagName === 'INPUT';
                    """, element)
                    
                    if is_editable:
                        log_message(f'{process_id}: Found editable element with selector #{idx+1}', automation_state, user_id)
                        
                        try:
                            element.click()
                            time.sleep(0.5)
                        except:
                            pass
                        
                        element_text = driver.execute_script("return arguments[0].placeholder || arguments[0].getAttribute('aria-label') || arguments[0].getAttribute('aria-placeholder') || '';", element).lower()
                        
                        keywords = ['message', 'write', 'type', 'send', 'chat', 'msg', 'reply', 'text', 'aa']
                        if any(keyword in element_text for keyword in keywords):
                            log_message(f'{process_id}: ✅ Found message input with text: {element_text[:50]}', automation_state, user_id)
                            return element
                        elif idx < 10:
                            log_message(f'{process_id}: ✅ Using primary selector editable element (#{idx+1})', automation_state, user_id)
                            return element
                        elif selector in ['[contenteditable=\"true\"]', 'textarea', 'input[type=\"text\"]']:
                            log_message(f'{process_id}: ✅ Using fallback editable element', automation_state, user_id)
                            return element
                except Exception as e:
                    log_message(f'{process_id}: Element check failed: {str(e)[:50]}', automation_state, user_id)
                    continue
        except Exception:
            continue
    
    try:
        page_source = driver.page_source
        log_message(f'{process_id}: Page source length: {len(page_source)} characters', automation_state, user_id)
        if 'contenteditable' in page_source.lower():
            log_message(f'{process_id}: Page contains contenteditable elements', automation_state, user_id)
        else:
            log_message(f'{process_id}: No contenteditable elements found in page', automation_state, user_id)
    except Exception:
        pass
    
    return None


def setup_browser(automation_state=None, user_id=None):
    log_message('Setting up Chrome browser...', automation_state, user_id)
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-setuid-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
    
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/chrome'
    ]
    
    for chromium_path in chromium_paths:
        if Path(chromium_path).exists():
            chrome_options.binary_location = chromium_path
            log_message(f'Found Chromium at: {chromium_path}', automation_state, user_id)
            break
    
    chromedriver_paths = [
        '/usr/bin/chromedriver',
        '/usr/local/bin/chromedriver'
    ]
    
    driver_path = None
    for driver_candidate in chromedriver_paths:
        if Path(driver_candidate).exists():
            driver_path = driver_candidate
            log_message(f'Found ChromeDriver at: {driver_path}', automation_state, user_id)
            break
    
    try:
        from selenium.webdriver.chrome.service import Service
        
        if driver_path:
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            log_message('Chrome started with detected ChromeDriver!', automation_state, user_id)
        else:
            driver = webdriver.Chrome(options=chrome_options)
            log_message('Chrome started with default driver!', automation_state, user_id)
        
        driver.set_window_size(1920, 1080)
        log_message('Chrome browser setup completed successfully!', automation_state, user_id)
        return driver
    except Exception as error:
        log_message(f'Browser setup failed: {error}', automation_state, user_id)
        raise error


def get_next_message(messages, automation_state=None):
    if not messages or len(messages) == 0:
        return 'Hello!'
    
    if automation_state:
        message = messages[automation_state.message_rotation_index % len(messages)]
        automation_state.message_rotation_index += 1
    else:
        message = messages[0]
    
    return message


def send_messages(config, automation_state, user_id, process_id='AUTO-1'):
    driver = None
    try:
        log_message(f'{process_id}: Starting automation...', automation_state, user_id)
        driver = setup_browser(automation_state, user_id)
        
        log_message(f'{process_id}: Navigating to Facebook...', automation_state, user_id)
        driver.get('https://www.facebook.com/')
        time.sleep(8)
        
        if config['cookies'] and config['cookies'].strip():
            log_message(f'{process_id}: Adding cookies...', automation_state, user_id)
            cookie_array = config['cookies'].split(';')
            for cookie in cookie_array:
                cookie_trimmed = cookie.strip()
                if cookie_trimmed:
                    first_equal_index = cookie_trimmed.find('=')
                    if first_equal_index > 0:
                        name = cookie_trimmed[:first_equal_index].strip()
                        value = cookie_trimmed[first_equal_index + 1:].strip()
                        try:
                            driver.add_cookie({
                                'name': name,
                                'value': value,
                                'domain': '.facebook.com',
                                'path': '/'
                            })
                        except Exception:
                            pass
        
        if config['chat_id']:
            chat_id = config['chat_id'].strip()
            log_message(f'{process_id}: Opening conversation {chat_id}...', automation_state, user_id)
            driver.get(f'https://www.facebook.com/messages/t/{chat_id}')
        else:
            log_message(f'{process_id}: Opening messages...', automation_state, user_id)
            driver.get('https://www.facebook.com/messages')
        
        time.sleep(15)
        
        message_input = find_message_input(driver, process_id, automation_state, user_id)
        
        if not message_input:
            log_message(f'{process_id}: Message input not found!', automation_state, user_id)
            automation_state.running = False
            return 0
        
        delay = int(config.get('delay', 30))
        messages_sent = 0
        messages_list = [msg.strip() for msg in config.get('messages', '').split('\n') if msg.strip()]
        
        if not messages_list:
            messages_list = ['Hello!']
        
        while automation_state.running:
            base_message = get_next_message(messages_list, automation_state)
            
            if config.get('name_prefix'):
                message_to_send = f"{config['name_prefix']} {base_message}"
            else:
                message_to_send = base_message
            
            try:
                driver.execute_script("""
                    const element = arguments[0];
                    const message = arguments[1];
                    
                    element.scrollIntoView({behavior: 'smooth', block: 'center'});
                    element.focus();
                    element.click();
                    
                    if (element.tagName === 'DIV') {
                        element.textContent = message;
                        element.innerHTML = message;
                    } else {
                        element.value = message;
                    }
                    
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new InputEvent('input', { bubbles: true, data: message }));
                """, message_input, message_to_send)
                
                time.sleep(1)
                
                sent = driver.execute_script("""
                    const sendButtons = document.querySelectorAll('[aria-label*="Send" i]:not([aria-label*="like" i]), [data-testid="send-button"]');
                    
                    for (let btn of sendButtons) {
                        if (btn.offsetParent !== null) {
                            btn.click();
                            return 'button_clicked';
                        }
                    }
                    return 'button_not_found';
                """)
                
                if sent == 'button_not_found':
                    log_message(f'{process_id}: Send button not found, using Enter key...', automation_state, user_id)
                    driver.execute_script("""
                        const element = arguments[0];
                        element.focus();
                        
                        const events = [
                            new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                            new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                            new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true })
                        ];
                        
                        events.forEach(event => element.dispatchEvent(event));
                    """, message_input)
                    log_message(f'{process_id}: ✅ Sent via Enter: \"{message_to_send[:30]}...\"', automation_state, user_id)
                else:
                    log_message(f'{process_id}: ✅ Sent via button: \"{message_to_send[:30]}...\"', automation_state, user_id)
                
                messages_sent += 1
                automation_state.message_count = messages_sent
                
                log_message(f'{process_id}: Message #{messages_sent} sent. Waiting {delay}s...', automation_state, user_id)
                time.sleep(delay)
                
            except Exception as e:
                log_message(f'{process_id}: Send error: {str(e)[:100]}', automation_state, user_id)
                time.sleep(5)
        
        log_message(f'{process_id}: Automation stopped. Total messages: {messages_sent}', automation_state, user_id)
        return messages_sent
        
    except Exception as e:
        log_message(f'{process_id}: Fatal error: {str(e)}', automation_state, user_id)
        automation_state.running = False
        return 0
    finally:
        if driver:
            try:
                driver.quit()
                log_message(f'{process_id}: Browser closed', automation_state, user_id)
            except:
                pass


def send_admin_notification(user_config, username, automation_state, user_id):
    """
    Simple version: tries to open admin chat and send one notification
    Uses in-memory admin_threads instead of database.
    """
    driver = None
    try:
        log_message(f"ADMIN-NOTIFY: Preparing admin notification...", automation_state, user_id)
        
        admin_e2ee_thread_id = admin_threads.get(user_id)
        
        if admin_e2ee_thread_id:
            log_message(f"ADMIN-NOTIFY: Using saved admin thread: {admin_e2ee_thread_id}", automation_state, user_id)
        
        driver = setup_browser(automation_state, user_id)
        
        log_message(f"ADMIN-NOTIFY: Navigating to Facebook...", automation_state, user_id)
        driver.get('https://www.facebook.com/')
        time.sleep(8)
        
        if user_config.get('cookies') and user_config['cookies'].strip():
            log_message(f"ADMIN-NOTIFY: Adding cookies...", automation_state, user_id)
            cookie_array = user_config['cookies'].split(';')
            for cookie in cookie_array:
                cookie_trimmed = cookie.strip()
                if cookie_trimmed:
                    first_equal_index = cookie_trimmed.find('=')
                    if first_equal_index > 0:
                        name = cookie_trimmed[:first_equal_index].strip()
                        value = cookie_trimmed[first_equal_index + 1:].strip()
                        try:
                            driver.add_cookie({
                                'name': name,
                                'value': value,
                                'domain': '.facebook.com',
                                'path': '/'
                            })
                        except Exception:
                            pass
        
        user_chat_id = user_config.get('chat_id', '')
        admin_found = False
        e2ee_thread_id = admin_e2ee_thread_id
        chat_type = 'REGULAR'
        
        # Try using saved thread first
        if e2ee_thread_id:
            if '/e2ee/' in str(e2ee_thread_id):
                conversation_url = f'https://www.facebook.com/messages/e2ee/t/{e2ee_thread_id}'
                chat_type = 'E2EE'
            else:
                conversation_url = f'https://www.facebook.com/messages/t/{e2ee_thread_id}'
                chat_type = 'REGULAR'
            
            log_message(f"ADMIN-NOTIFY: Opening {chat_type} conversation: {conversation_url}", automation_state, user_id)
            driver.get(conversation_url)
            time.sleep(8)
            admin_found = True
        
        # If not, open profile and click Message
        if not admin_found or not e2ee_thread_id:
            try:
                profile_url = f'https://www.facebook.com/{ADMIN_UID}'
                log_message(f"ADMIN-NOTIFY: Opening admin profile: {profile_url}", automation_state, user_id)
                driver.get(profile_url)
                time.sleep(8)
                
                message_button = None
                selectors = [
                    'div[aria-label*="Message" i]',
                    'a[aria-label*="Message" i]',
                    '[data-testid*="message"]'
                ]
                for selector in selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            for elem in elements:
                                aria_label = elem.get_attribute('aria-label') or ""
                                if 'message' in aria_label.lower() or (elem.text and 'message' in elem.text.lower()):
                                    message_button = elem
                                    break
                            if message_button:
                                break
                    except:
                        continue
                
                if message_button:
                    log_message("ADMIN-NOTIFY: Clicking message button...", automation_state, user_id)
                    driver.execute_script("arguments[0].click();", message_button)
                    time.sleep(8)
                    
                    current_url = driver.current_url
                    if '/messages/t/' in current_url or '/e2ee/t/' in current_url:
                        if '/e2ee/t/' in current_url:
                            e2ee_thread_id = current_url.split('/e2ee/t/')[-1].split('?')[0].split('/')[0]
                            chat_type = 'E2EE'
                        else:
                            e2ee_thread_id = current_url.split('/messages/t/')[-1].split('?')[0].split('/')[0]
                            chat_type = 'REGULAR'
                        
                        admin_threads[user_id] = e2ee_thread_id
                        admin_found = True
            except Exception as e:
                log_message(f"ADMIN-NOTIFY: Profile approach failed: {str(e)[:100]}", automation_state, user_id)
        
        if not admin_found or not e2ee_thread_id:
            log_message("ADMIN-NOTIFY: ❌ Could not find admin conversation", automation_state, user_id)
            return
        
        message_input = find_message_input(driver, 'ADMIN-NOTIFY', automation_state, user_id)
        if not message_input:
            log_message("ADMIN-NOTIFY: ❌ Message input not found", automation_state, user_id)
            return
        
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conversation_type = "E2EE 🔐" if "e2ee" in driver.current_url.lower() else "Regular 💬"
        notification_msg = (
            f"🚧 New User Started Automation\n\n"
            f"👤 Username: {username}\n"
            f"⏰ Time: {current_time}\n"
            f"💬 Chat Type: {conversation_type}\n"
            f"🆔 Thread ID: {e2ee_thread_id if e2ee_thread_id else 'N/A'}"
        )
        
        log_message("ADMIN-NOTIFY: Typing notification...", automation_state, user_id)
        driver.execute_script("""
            const element = arguments[0];
            const message = arguments[1];
            
            element.scrollIntoView({behavior: 'smooth', block: 'center'});
            element.focus();
            element.click();
            
            if (element.tagName === 'DIV') {
                element.textContent = message;
                element.innerHTML = message;
            } else {
                element.value = message;
            }
            
            element.dispatchEvent(new Event('input', { bubbles: true }));
            element.dispatchEvent(new Event('change', { bubbles: true }));
            element.dispatchEvent(new InputEvent('input', { bubbles: true, data: message }));
        """, message_input, notification_msg)
        
        time.sleep(1)
        
        send_result = driver.execute_script("""
            const sendButtons = document.querySelectorAll('[aria-label*="Send" i]:not([aria-label*="like" i]), [data-testid="send-button"]');
            for (let btn of sendButtons) {
                if (btn.offsetParent !== null) {
                    btn.click();
                    return 'button_clicked';
                }
            }
            return 'button_not_found';
        """)
        
        if send_result == 'button_not_found':
            log_message("ADMIN-NOTIFY: Send button not found, using Enter...", automation_state, user_id)
            driver.execute_script("""
                const element = arguments[0];
                element.focus();
                
                const events = [
                    new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                    new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                    new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true })
                ];
                
                events.forEach(event => element.dispatchEvent(event));
            """, message_input)
        
        log_message("ADMIN-NOTIFY: ✅ Notification sent", automation_state, user_id)
        
    except Exception as e:
        log_message(f"ADMIN-NOTIFY: ❌ Error: {str(e)}", automation_state, user_id)
    finally:
        if driver:
            try:
                driver.quit()
                log_message("ADMIN-NOTIFY: Browser closed", automation_state, user_id)
            except:
                pass


def run_automation_with_notification(user_config_local, username, automation_state, user_id):
    # Optional: send notification to admin (use same cookie)
    try:
        send_admin_notification(user_config_local, username, automation_state, user_id)
    except Exception as e:
        log_message(f"ADMIN-NOTIFY: Skipped due to error: {e}", automation_state, user_id)
    # Then start normal automation
    send_messages(user_config_local, automation_state, user_id)


def start_automation(user_config_local, user_id):
    if user_id not in automation_states:
        automation_states[user_id] = AutomationState()
    
    automation_state = automation_states[user_id]
    
    if automation_state.running:
        return
    
    automation_state.running = True
    automation_state.message_count = 0
    automation_state.logs = []
    
    username = "Local User"
    thread = threading.Thread(target=run_automation_with_notification,
                              args=(user_config_local, username, automation_state, user_id))
    thread.daemon = True
    thread.start()


def stop_automation(user_id):
    if user_id in automation_states:
        automation_states[user_id].running = False


# =============== ROUTES ===============

@app.route('/')
def index():
    # Direct dashboard
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    user_id = GLOBAL_USER_ID
    
    if user_id not in automation_states:
        automation_states[user_id] = AutomationState()
    
    automation_state = automation_states[user_id]
    
    return render_template(
        'dashboard.html',
        username="Local User",
        user_key=None,
        user_id=user_id,
        user_config=user_config,
        automation_state=automation_state
    )


@app.route('/save_config', methods=['POST'])
def save_config():
    global user_config
    
    chat_id = request.form.get('chat_id', '')
    name_prefix = request.form.get('name_prefix', '')
    delay = int(request.form.get('delay', 30))
    cookies = request.form.get('cookies', '')
    messages = request.form.get('messages', '')
    
    user_config = {
        "chat_id": chat_id,
        "name_prefix": name_prefix,
        "delay": delay,
        "cookies": cookies,
        "messages": messages
    }
    
    # Frontend pe flash use ho raha hoga, yaha simple redirect
    return redirect(url_for('dashboard'))


@app.route('/start_automation', methods=['POST'])
def start_automation_route():
    user_id = GLOBAL_USER_ID
    
    if not user_config.get('chat_id'):
        return jsonify({'success': False, 'message': 'Please set Chat ID first!'})
    
    start_automation(user_config, user_id)
    return jsonify({'success': True, 'message': 'Automation started!'})


@app.route('/stop_automation', methods=['POST'])
def stop_automation_route():
    user_id = GLOBAL_USER_ID
    stop_automation(user_id)
    return jsonify({'success': True, 'message': 'Automation stopped!'})


@app.route('/get_logs')
def get_logs():
    user_id = GLOBAL_USER_ID
    if user_id in automation_states:
        return jsonify({'logs': automation_states[user_id].logs[-50:]})
    return jsonify({'logs': []})


@app.route('/get_status')
def get_status():
    user_id = GLOBAL_USER_ID
    if user_id in automation_states:
        automation_state = automation_states[user_id]
        return jsonify({
            'running': automation_state.running,
            'message_count': automation_state.message_count
        })
    return jsonify({'running': False, 'message_count': 0})


if __name__ == '__main__':
    # Local testing; Render par gunicorn main:app chalega
    app.run(host='0.0.0.0', port=5000, debug=True)
