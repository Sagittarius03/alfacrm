# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime, timedelta
import threading
import requests

class AlfaCRMApi:
    def __init__(self, config):
        self.config = config
        self.driver = None
        self.is_logged_in = False
        self.lock = threading.Lock()
        self.session = requests.Session()
        
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920x1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except:
            if self.config.get('chromedriver_path'):
                from selenium.webdriver.chrome.service import Service
                service = Service(self.config['chromedriver_path'])
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            
        self.driver.set_page_load_timeout(30)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def login(self):
        if self.is_logged_in:
            return True
            
        try:
            saved_cookies = self.db.get_session_cookies() if hasattr(self, 'db') else []
            if saved_cookies:
                print("Попытка восстановления сессии...")
                if not self.driver:
                    self.setup_driver()
                self.driver.get(self.config['site_url'])
                for cookie in saved_cookies:
                    try:
                        clean_cookie = {k: v for k, v in cookie.items() if k in ['name', 'value', 'domain', 'path', 'expiry', 'httpOnly', 'secure']}
                        if 'expiry' in clean_cookie and isinstance(clean_cookie['expiry'], str):
                            clean_cookie['expiry'] = int(clean_cookie['expiry'])
                        self.driver.add_cookie(clean_cookie)
                    except Exception as e:
                        print(f"Ошибка добавления cookie {cookie.get('name')}: {e}")
                self.driver.refresh()
                time.sleep(2)
                if self.check_login_success():
                    self.is_logged_in = True
                    print("Сессия восстановлена успешно")
                    return True
                else:
                    print("Сохранённая сессия недействительна, выполняем полный вход")
            
            if not self.driver:
                self.setup_driver()
            print(f"Логин на {self.config['site_url']}")
            self.driver.get(self.config['site_url'])
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "login-form"))
            )
            username_field = self.driver.find_element(By.ID, "loginform-username")
            password_field = self.driver.find_element(By.ID, "loginform-password")
            username_field.clear()
            username_field.send_keys(self.config['username'])
            password_field.clear()
            password_field.send_keys(self.config['password'])
            
            # Устанавливаем галочку "Запомнить меня"
            try:
                remember_me = self.driver.find_element(By.ID, "loginform-rememberme")
                if not remember_me.is_selected():
                    remember_me.click()
            except:
                pass
            
            submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[name='login-button']")
            submit_button.click()
            time.sleep(3)
            
            if self.check_2fa_required():
                print("Требуется код подтверждения")
                code = self.get_verification_code()
                if not code:
                    print("Введите код вручную:")
                    code = input("Код: ").strip()
                if code and self.enter_2fa_code(code):
                    self.is_logged_in = True
                    print("Успешный вход с 2FA")
                else:
                    print("Ошибка ввода кода")
                    return False
            else:
                if self.check_login_success():
                    self.is_logged_in = True
                    print("Успешный вход")
                else:
                    print("Не удалось войти")
                    return False
            
            if self.is_logged_in and hasattr(self, 'db'):
                cookies = self.driver.get_cookies()
                self.db.save_session_cookies(cookies)
                print("Сессия сохранена")
            
            return self.is_logged_in
            
        except Exception as e:
            print(f"Ошибка при входе: {e}")
            return False        
    def check_2fa_required(self):
        try:
            selectors = [
                "#login2faform-code",
                "#loginform-verificationcode",
                "[name='LoginForm[verificationcode]']",
                "[name='Login2FAForm[code]']",
                "input[name='code']",
            ]
            for selector in selectors:
                try:
                    self.driver.find_element(By.CSS_SELECTOR, selector)
                    return True
                except:
                    continue
            try:
                self.driver.find_element(By.XPATH, "//*[contains(text(), 'код') or contains(text(), 'Код') or contains(text(), 'code')]")
                return True
            except:
                pass
            return False
        except Exception as e:
            print(f"Ошибка проверки 2FA: {e}")
            return False
            
    def get_verification_code(self):
        if self.config.get('verification_code'):
            return self.config['verification_code']
        if self.config.get('email_imap'):
            try:
                import imaplib
                import email
                imap_config = self.config.get('email_imap', {})
                if not imap_config.get('server') or not imap_config.get('email') or not imap_config.get('password'):
                    return None
                mail = imaplib.IMAP4_SSL(imap_config.get('server'))
                mail.login(imap_config.get('email'), imap_config.get('password'))
                mail.select('INBOX')
                status, messages = mail.search(None, 'UNSEEN')
                if status == 'OK':
                    for num in messages[0].split()[-5:]:
                        status, data = mail.fetch(num, '(RFC822)')
                        if status == 'OK':
                            msg = email.message_from_bytes(data[0][1])
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    content_type = part.get_content_type()
                                    content_disposition = str(part.get("Content-Disposition"))
                                    if content_type == "text/plain" and "attachment" not in content_disposition:
                                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                            patterns = [
                                r'код\s*:\s*(\d{6})',
                                r'(\d{6})\s*[-–]\s*ваш\s*код',
                                r'код\s+подтверждения\s*[:;]\s*(\d{6})',
                                r'verification\s+code\s*[:;]\s*(\d{6})',
                                r'\b(\d{6})\b'
                            ]
                            for pattern in patterns:
                                code_match = re.search(pattern, body, re.IGNORECASE)
                                if code_match:
                                    mail.close()
                                    mail.logout()
                                    return code_match.group(1)
                mail.close()
                mail.logout()
                return None
            except Exception as e:
                print(f"Ошибка получения кода из почты: {e}")
                return None
        return None
        
    def enter_2fa_code(self, code):
        try:
            selectors = [
                "#login2faform-code",
                "#loginform-verificationcode",
                "[name='LoginForm[verificationcode]']",
                "[name='Login2FAForm[code]']",
                "input[name='code']",
            ]
            code_field = None
            for selector in selectors:
                try:
                    code_field = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except:
                    continue
            if not code_field:
                print("Не найдено поле для ввода кода")
                self.save_page_source("2fa_error.html")
                return False
            code_field.clear()
            code_field.send_keys(code)
            submit_selectors = [
                "button[type='submit']",
                "button[name='login-button']",
                "//button[contains(text(), 'Log in')]",
                "//button[contains(text(), 'Войти')]",
            ]
            submit_button = None
            for selector in submit_selectors:
                try:
                    if selector.startswith('//'):
                        submit_button = self.driver.find_element(By.XPATH, selector)
                    else:
                        submit_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except:
                    continue
            if submit_button:
                submit_button.click()
            else:
                code_field.submit()
            time.sleep(3)
            return self.check_login_success()
        except Exception as e:
            print(f"Ошибка ввода кода: {e}")
            return False
            
    def check_login_success(self):
        try:
            selectors = [".navbar-top-links", ".profile-link", "#side-menu", ".teacher-menu", ".user-menu"]
            for selector in selectors:
                try:
                    self.driver.find_element(By.CSS_SELECTOR, selector)
                    return True
                except:
                    continue
            current_url = self.driver.current_url
            if "dashboard" in current_url or "calendar" in current_url or "teacher" in current_url:
                return True
            return False
        except Exception as e:
            print(f"Ошибка проверки входа: {e}")
            return False
            
    def get_lessons_from_api(self, start_date=None, end_date=None):
        if not self.is_logged_in:
            if not self.login():
                return []
        try:
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                self.session.cookies.set(cookie['name'], cookie['value'])
            try:
                csrf_token = self.driver.find_element(By.CSS_SELECTOR, "meta[name='csrf-token']").get_attribute('content')
            except:
                csrf_token = None
            if not start_date:
                start_date = datetime.now().strftime("%Y-%m-%d")
            if not end_date:
                end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            url = f"{self.config['site_url']}/teacher/1/calendar/fetch"
            params = {'start': start_date, 'end': end_date, 'page': 1}
            headers = {}
            if csrf_token:
                headers['X-CSRF-Token'] = csrf_token
            headers['X-Requested-With'] = 'XMLHttpRequest'
            headers['Referer'] = self.config['site_url'] + '/teacher/1/calendar/index'
            all_lessons = []
            page = 1
            total = None
            while True:
                params['page'] = page
                response = self.session.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if total is None:
                        total = data.get('total', 0)
                    lessons_data = data.get('collection', [])
                    all_lessons.extend(lessons_data)
                    if len(all_lessons) >= total or not lessons_data:
                        break
                    page += 1
                else:
                    break
            lessons = []
            for lesson_data in all_lessons:
                lesson = self.parse_api_lesson(lesson_data)
                if lesson:
                    lessons.append(lesson)
            print(f"Найдено {len(lessons)} уроков через API")
            return lessons
        except Exception as e:
            print(f"Ошибка получения уроков через API: {e}")
            return self.get_lessons_from_page(start_date, end_date)
            
    def get_lessons_from_page(self, start_date=None, end_date=None):
        if not self.is_logged_in:
            if not self.login():
                return []
        try:
            if not start_date:
                start_date = datetime.now().strftime("%Y-%m-%d")
            calendar_url = self.config.get('schedule_url', '/teacher/1/calendar/index')
            full_url = f"{self.config['site_url']}{calendar_url}"
            if not full_url.startswith('http'):
                full_url = self.config['site_url'] + calendar_url
            self.driver.get(full_url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "fc-view-container"))
            )
            time.sleep(2)
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            lessons = []
            events = soup.select('.fc-time-grid-event, .fc-event')
            for event in events:
                lesson = self.parse_page_lesson(event, start_date)
                if lesson:
                    lessons.append(lesson)
            print(f"Найдено {len(lessons)} уроков на странице")
            return lessons
        except Exception as e:
            print(f"Ошибка получения уроков со страницы: {e}")
            return []
            
    def parse_api_lesson(self, data):
        try:
            status_map = {1: 'scheduled', 2: 'cancelled', 3: 'completed'}
            status = status_map.get(data.get('status'), 'scheduled')
            type_map = {1: 'individual', 2: 'group', 3: 'trial', 4: 'tech_support'}
            lesson_type = type_map.get(data.get('type'), 'unknown')
            
            # Извлечение customer_id
            customer_id = None
            customers = data.get('customers', {})
            if isinstance(customers, dict):
                customer_ids = list(customers.keys())
                customer_id = customer_ids[0] if customer_ids else None
            elif isinstance(customers, list):
                for c in customers:
                    if isinstance(c, dict) and 'id' in c:
                        customer_id = c['id']
                        break
            if not customer_id:
                customer_id = data.get('customer_id') or data.get('client_id')
            if not customer_id and data.get('link'):
                match = re.search(r'customer/view\?id=(\d+)', data.get('link', ''))
                if match:
                    customer_id = match.group(1)
            
            client_names = []
            if isinstance(customers, dict):
                client_names = list(customers.values())
            elif isinstance(customers, list):
                client_names = [c.get('name', '') for c in customers if isinstance(c, dict)]
            
            # Время: начало, длительность, конец
            start_time = data.get('start', '')
            duration = data.get('duration', 0)  # в минутах
            time_start_str = ''
            time_end_str = ''
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    time_start_str = dt.strftime("%H:%M")
                    if duration:
                        dt_end = dt + timedelta(minutes=duration)
                        time_end_str = dt_end.strftime("%H:%M")
                        time_str = f"{time_start_str} - {time_end_str}"
                    else:
                        time_str = time_start_str
                except:
                    time_str = start_time[:5] if len(start_time) >= 5 else ''
            else:
                time_str = ''
            
            lesson = {
                'id': str(data.get('id', '')),
                'time': time_str,  # диапазон или только начало
                'time_start': time_start_str,
                'time_end': time_end_str,
                'duration': duration,
                'client': ', '.join(client_names) if client_names else data.get('title', ''),
                'subject': data.get('subject', ''),
                'comment': data.get('note', ''),
                'status': status,
                'link': f"{self.config['site_url']}/teacher/1/calendar/index?date={data.get('date', '')}",
                'teacher': data.get('teacher', ''),
                'room': str(data.get('room', '')),
                'type': lesson_type,
                'is_occupied': status in ['scheduled', 'completed'],
                'date': data.get('date', ''),
                'timestamp': datetime.now().isoformat(),
                'customer_id': customer_id,
            }
            return lesson
        except Exception as e:
            print(f"Ошибка парсинга API урока: {e}")
            return None       
    
    def parse_page_lesson(self, element, date):
        try:
            time_elem = element.select_one('.fc-time')
            time_text = time_elem.text.strip() if time_elem else ''
            time_match = re.search(r'(\d{1,2}:\d{2})', time_text)
            time_str = time_match.group(1) if time_match else ''
            title_elem = element.select_one('.fc-title')
            title_text = title_elem.text.strip() if title_elem else ''
            classes = element.get('class', [])
            status = 'scheduled'
            if 'status2' in classes:
                status = 'cancelled'
            elif 'status3' in classes:
                status = 'completed'
            icon_elem = element.select_one('.fc-title i')
            lesson_type = 'unknown'
            if icon_elem:
                icon_class = icon_elem.get('class', [])
                if 'ion-asterisk' in icon_class:
                    lesson_type = 'trial'
                elif 'ion-person' in icon_class:
                    lesson_type = 'individual'
                elif 'ion-person-stalker' in icon_class:
                    lesson_type = 'group'
                elif 'ion-wrench' in icon_class:
                    lesson_type = 'tech_support'
            client_match = re.search(r'([A-Za-zА-Яа-я\s]+)\s*\([^)]+\)', title_text)
            client = client_match.group(1).strip() if client_match else title_text
            teacher_match = re.search(r'<i[^>]*class="[^"]*ion-university[^"]*"[^>]*>([^<]+)</i>', str(title_elem)) if title_elem else None
            teacher = teacher_match.group(1).strip() if teacher_match else ''
            room_match = re.search(r'room-(\d+)', ' '.join(classes))
            room = room_match.group(1) if room_match else ''
            lesson_id = element.get('data-id', '') or element.get('id', '')
            lesson = {
                'id': lesson_id,
                'time': time_str,
                'client': client,
                'subject': '',
                'comment': '',
                'status': status,
                'link': self.config['site_url'] + '/teacher/1/calendar/index',
                'teacher': teacher,
                'room': room,
                'type': lesson_type,
                'is_occupied': status in ['scheduled', 'completed'],
                'date': date or datetime.now().strftime("%Y-%m-%d"),
                'timestamp': datetime.now().isoformat()
            }
            return lesson
        except Exception as e:
            print(f"Ошибка парсинга страницы урока: {e}")
            return None
            
    def get_lessons_schedule(self, date=None):
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        if not self.is_logged_in:
            if not self.login():
                return []
        lessons = self.get_lessons_from_api(date, date)
        if not lessons:
            lessons = self.get_lessons_from_page(date, date)
        return lessons
        
    def get_all_lessons_for_period(self, start_date, end_date):
        if not self.is_logged_in:
            if not self.login():
                return []
        lessons = self.get_lessons_from_api(start_date, end_date)
        if not lessons:
            all_lessons = []
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime("%Y-%m-%d")
                day_lessons = self.get_lessons_from_page(date_str, date_str)
                all_lessons.extend(day_lessons)
                current_date += timedelta(days=1)
            lessons = all_lessons
        return lessons
        
    def save_page_source(self, filename="page_source.html"):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            print(f"Сохранено в {filename}")
            return True
        except Exception as e:
            print(f"Ошибка сохранения: {e}")
            return False
            
    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            self.is_logged_in = False