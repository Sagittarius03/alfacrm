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
    def __init__(self, config, crm_type='rts'):
        self.config = config
        self.crm_type = crm_type
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
        with self.lock:
            if self.is_logged_in:
                return True
                
            try:
                saved_cookies = self.db.get_session_cookies(self.crm_type) if hasattr(self, 'db') else []
                if saved_cookies:
                    print(f"Попытка восстановления сессии для {self.crm_type}...")
                    if not self.driver:
                        self.setup_driver()
                    self.driver.get(self.config['site_url'])
                    current_domain = self.config['site_url'].replace('https://', '').replace('http://', '').split('/')[0]
                    for cookie in saved_cookies:
                        if cookie.get('domain') and current_domain not in cookie['domain']:
                            print(f"Пропускаем cookie {cookie.get('name')} с доменом {cookie.get('domain')}")
                            continue
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
                        print(f"Сессия восстановлена для {self.crm_type}")
                        return True
                    else:
                        print(f"Сохранённая сессия для {self.crm_type} недействительна")
                
                if not self.driver:
                    self.setup_driver()
                print(f"Логин на {self.config['site_url']} ({self.crm_type})")
                self.driver.get(self.config['site_url'])
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.ID, "login-form"))
                )
                username_field = self.driver.find_element(By.ID, "loginform-username")
                password_field = self.driver.find_element(By.ID, "loginform-password")
                username_field.clear()
                username_field.send_keys(self.config['username'])
                password_field.clear()
                password_field.send_keys(self.config['password'])
                
                try:
                    remember_me = self.driver.find_element(By.ID, "loginform-rememberme")
                    if not remember_me.is_selected():
                        remember_me.click()
                except:
                    pass
                
                submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[name='login-button']")
                submit_button.click()
                time.sleep(2)
                
                if self.check_2fa_required():
                    print(f"Требуется код подтверждения для {self.crm_type}")
                    code = self.get_verification_code()
                    if not code:
                        print("Введите код вручную:")
                        code = input("Код: ").strip()
                    if code and self.enter_2fa_code(code):
                        self.is_logged_in = True
                        print(f"Успешный вход с 2FA для {self.crm_type}")
                    else:
                        print("Ошибка ввода кода")
                        return False
                else:
                    if self.check_login_success():
                        self.is_logged_in = True
                        print(f"Успешный вход для {self.crm_type}")
                    else:
                        try:
                            error = self.driver.find_element(By.CSS_SELECTOR, ".alert-danger")
                            print(f"Ошибка входа: {error.text}")
                        except:
                            pass
                        print(f"Не удалось войти для {self.crm_type}")
                        return False
                
                if self.is_logged_in and hasattr(self, 'db'):
                    cookies = self.driver.get_cookies()
                    self.db.save_session_cookies(cookies, self.crm_type)
                    print(f"Сессия сохранена для {self.crm_type}")
                
                return self.is_logged_in
                
            except Exception as e:
                print(f"Ошибка при входе для {self.crm_type}: {e}")
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
            # Находим поле для кода
            code_field = None
            selectors = [
                "#login2faform-code",
                "#loginform-verificationcode",
                "[name='LoginForm[verificationcode]']",
                "[name='Login2FAForm[code]']",
                "input[name='code']",
            ]
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

            # Находим кнопку отправки
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

            # Ожидаем либо успешного входа, либо появления сообщения об ошибке
            # Даём больше времени на обработку (20 секунд)
            time.sleep(2)
            
            # Проверяем несколько раз с интервалом
            for i in range(10):
                time.sleep(1)
                if self.check_login_success():
                    return True
                # Проверяем, не появилось ли сообщение об ошибке
                try:
                    error = self.driver.find_element(By.CSS_SELECTOR, ".alert-danger, .error-message")
                    if error.is_displayed():
                        print(f"Ошибка входа после 2FA: {error.text}")
                        return False
                except:
                    pass
                
                # Проверяем, не перенаправило ли нас на страницу логина снова
                current_url = self.driver.current_url
                if 'login' not in current_url.lower():
                    return True
            
            return False

        except Exception as e:
            print(f"Ошибка ввода кода: {e}")
            return False
            
    def check_login_success(self):
        try:
            # Проверяем URL – если он не содержит 'login', считаем вход успешным
            current_url = self.driver.current_url
            if 'login' not in current_url.lower():
                return True
            
            # Проверяем наличие элемента, характерного для авторизованного пользователя
            # В разных CRM могут быть разные селекторы
            selectors = [
                ".navbar-top-links", 
                ".profile-link", 
                "#side-menu", 
                ".teacher-menu", 
                ".user-menu", 
                ".logout",
                ".dropdown.user-menu",
                ".header-user",
                ".avatar"
            ]
            for selector in selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element.is_displayed():
                        return True
                except:
                    continue
            
            # Проверяем наличие кнопки выхода
            try:
                logout_links = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'Выход') or contains(text(), 'Logout')]")
                if logout_links and logout_links[0].is_displayed():
                    return True
            except:
                pass
            
            return False
        except Exception as e:
            print(f"Ошибка проверки входа: {e}")
            return False
    
    def is_error_present(self):
        try:
            # Ищем сообщение об ошибке (например, alert-danger)
            error = self.driver.find_element(By.CSS_SELECTOR, ".alert-danger, .error-message")
            return error.is_displayed()
        except:
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
            print(f"Найдено {len(lessons)} уроков через API для {self.crm_type}")
            return lessons
        except Exception as e:
            print(f"Ошибка получения уроков через API для {self.crm_type}: {e}")
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
            status_map = {
                '1': 'scheduled',
                '2': 'cancelled',
                '3': 'completed',
                '4': 'rescheduled'
            }
            status = status_map.get(str(data.get('status')), 'scheduled')
            
            type_map = {
                '1': 'individual',
                '2': 'group',
                '3': 'trial',
                '4': 'tech_support',
                '5': 'trial'
            }
            lesson_type = type_map.get(str(data.get('type')), 'unknown')
            
            # Извлечение учеников с деталями
            customers = data.get('customers', {})
            students = []
            customer_id = None
            
            # Извлечение ID группы
            group_id = data.get('group_id')
            if not group_id and data.get('group'):
                group_id = data.get('group')
            if not group_id and data.get('link'):
                group_match = re.search(r'group/view\?id=(\d+)', data.get('link', ''))
                if group_match:
                    group_id = group_match.group(1)
            
            # Извлечение названия группы
            group_name = None
            if data.get('group_name'):
                group_name = data.get('group_name')
            elif data.get('link'):
                # Пробуем извлечь из текста
                group_match = re.search(r'Группа\s*[:\-]?\s*([^<,\n]+)', data.get('title', ''), re.IGNORECASE)
                if group_match:
                    group_name = group_match.group(1).strip()
            
            if isinstance(customers, dict):
                for cid, name_html in customers.items():
                    clean_name = re.sub(r'<[^>]+>', '', name_html).strip()
                    
                    # Определяем статусы
                    is_cancelled = '<strike' in name_html
                    is_absent = 'text-muted' in name_html or 'не спис' in name_html
                    is_rescheduled = 'Перенос' in name_html or 'rescheduled' in name_html.lower()
                    pause_match = re.search(r'\(пауза\s+([^)]+)\)', name_html)
                    is_paused = bool(pause_match)
                    pause_info = pause_match.group(1) if pause_match else None
                    is_completed = status == 'completed'
                    
                    # Остаток
                    balance_match = re.search(r'\((\d+)\s*(?:ост\.?|уроков?|осталось)\)', name_html, re.IGNORECASE)
                    balance = int(balance_match.group(1)) if balance_match else None
                    
                    extra_match = re.search(r'\(([^)]*(?:ост\.?|уроков?|осталось)[^)]*)\)', name_html, re.IGNORECASE)
                    extra_info = extra_match.group(1) if extra_match else ''
                    
                    student_data = {
                        'id': cid,
                        'name': clean_name,
                        'is_cancelled': is_cancelled,
                        'is_paused': is_paused,
                        'pause_info': pause_info,
                        'extra_info': extra_info,
                        'balance': balance,
                        'is_rescheduled': is_rescheduled,
                        'is_absent': is_absent,
                        'is_completed': is_completed,
                        'group_id': group_id,
                        'group_name': group_name
                    }
                    students.append(student_data)
                    
                    # Сохраняем остаток в БД
                    if balance is not None and hasattr(self, 'db'):
                        self.db.save_lesson_balance(
                            customer_id=cid,
                            customer_name=clean_name,
                            balance=balance,
                            crm_type=self.crm_type,
                            site_url=self.config['site_url']
                        )
                    
                    if not customer_id:
                        customer_id = cid
                        
            elif isinstance(customers, list):
                for item in customers:
                    if isinstance(item, dict):
                        cid = item.get('id')
                        name_html = item.get('name', '')
                        clean_name = re.sub(r'<[^>]+>', '', name_html).strip()
                        
                        is_cancelled = '<strike' in name_html
                        is_absent = 'text-muted' in name_html or 'не спис' in name_html
                        is_rescheduled = 'Перенос' in name_html or 'rescheduled' in name_html.lower()
                        pause_match = re.search(r'\(пауза\s+([^)]+)\)', name_html)
                        is_paused = bool(pause_match)
                        pause_info = pause_match.group(1) if pause_match else None
                        is_completed = status == 'completed'
                        
                        balance_match = re.search(r'\((\d+)\s*(?:ост\.?|уроков?|осталось)\)', name_html, re.IGNORECASE)
                        balance = int(balance_match.group(1)) if balance_match else None
                        
                        extra_match = re.search(r'\(([^)]*(?:ост\.?|уроков?|осталось)[^)]*)\)', name_html, re.IGNORECASE)
                        extra_info = extra_match.group(1).strip() if extra_match else ''
                        
                        student_data = {
                            'id': cid,
                            'name': clean_name,
                            'is_cancelled': is_cancelled,
                            'is_paused': is_paused,
                            'pause_info': pause_info,
                            'extra_info': extra_info,
                            'balance': balance,
                            'is_rescheduled': is_rescheduled,
                            'is_absent': is_absent,
                            'is_completed': is_completed,
                            'group_id': group_id,
                            'group_name': group_name
                        }
                        students.append(student_data)
                        
                        if balance is not None and hasattr(self, 'db'):
                            self.db.save_lesson_balance(
                                customer_id=cid,
                                customer_name=clean_name,
                                balance=balance,
                                crm_type=self.crm_type,
                                site_url=self.config['site_url']
                            )
                        
                        if not customer_id:
                            customer_id = cid
            
            if not customer_id:
                customer_id = data.get('customer_id') or data.get('client_id')
            if not customer_id and data.get('link'):
                match = re.search(r'customer/view\?id=(\d+)', data.get('link', ''))
                if match:
                    customer_id = match.group(1)
            
            # Собираем имена клиентов
            client_names = []
            if isinstance(customers, dict):
                client_names = [re.sub(r'<[^>]+>', '', v).strip() for v in customers.values()]
            elif isinstance(customers, list):
                client_names = [re.sub(r'<[^>]+>', '', c.get('name', '')).strip() for c in customers if isinstance(c, dict)]
            
            # Время
            start_time = data.get('start', '')
            duration = data.get('duration', 0)
            time_str = ''
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
            
            lesson = {
                'id': str(data.get('id', f"{self.crm_type}_{datetime.now().timestamp()}")),
                'time': time_str,
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
                'crm_type': self.crm_type,
                'site_url': self.config['site_url'],
                'students': students,
                'group_id': group_id,
                'group_name': group_name
            }
            
            # Сохраняем связи в БД
            if hasattr(self, 'db'):
                self.save_lesson_relations(lesson, students, group_id)
            
            return lesson
        except Exception as e:
            print(f"Ошибка парсинга API урока: {e}")
            import traceback
            traceback.print_exc()
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
            if 'status4' in classes or 'rescheduled' in classes:
                status = 'rescheduled'
            elif 'status2' in classes:
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
    
    # alfacrm_api.py - Добавляем методы для сохранения связей

    # alfacrm_api.py - Добавляем методы для сохранения связей

    def save_lesson_relations(self, lesson, students, group_id=None):
        """Сохраняет связи урока с учениками и группами"""
        try:
            lesson_id = lesson.get('id')
            crm_type = lesson.get('crm_type')
            site_url = lesson.get('site_url')
            lesson_status = lesson.get('status')
            is_completed = lesson_status == 'completed'
            
            # Сохраняем группу если есть
            if group_id and hasattr(self, 'db'):
                # Ищем название группы
                group_name = None
                # Пытаемся найти в данных урока
                if lesson.get('group_name'):
                    group_name = lesson.get('group_name')
                else:
                    # Ищем в students
                    for s in students:
                        if s.get('group_id') == group_id and s.get('group_name'):
                            group_name = s.get('group_name')
                            break
                
                # Если все еще нет, пробуем извлечь из названия
                if not group_name:
                    # Пробуем извлечь из client_text
                    client_text = lesson.get('client', '')
                    group_match = re.search(r'групп[аы]?\s*([^\d,]+)', client_text, re.IGNORECASE)
                    if group_match:
                        group_name = group_match.group(1).strip()
                    else:
                        # Используем ID как название
                        group_name = f"Группа #{group_id}"
                
                if group_name:
                    self.db.save_group(group_id, group_name, site_url, crm_type)
                    self.db.save_lesson_group(lesson_id, group_id)
            
            # Сохраняем учеников и связи
            for student in students:
                student_id = student.get('id')
                student_name = student.get('name', '')
                
                if student_id and hasattr(self, 'db'):
                    # Сохраняем ученика
                    balance = student.get('balance')
                    student_status = 'active'
                    if student.get('is_paused'):
                        student_status = 'paused'
                    elif student.get('is_cancelled'):
                        student_status = 'cancelled'
                    
                    self.db.save_student(
                        student_id=student_id,
                        name=student_name,
                        status=student_status,
                        balance=balance,
                        site_url=site_url,
                        crm_type=crm_type
                    )
                    
                    # Определяем статус на уроке
                    status_on_lesson = None
                    extra_info = student.get('extra_info', '')
                    pause_info = student.get('pause_info', '')
                    
                    # Проверяем статусы
                    if pause_info:
                        status_on_lesson = 'пауза'
                    elif 'абон' in extra_info.lower() or 'спис' in extra_info.lower():
                        status_on_lesson = 'списывать'
                    elif 'не спис' in extra_info.lower():
                        status_on_lesson = 'не списывать'
                    
                    # Получаем флаги
                    is_cancelled = student.get('is_cancelled', False)
                    is_paused = student.get('is_paused', False)
                    is_absent = student.get('is_absent', False)
                    is_rescheduled = student.get('is_rescheduled', False)
                    is_completed_flag = is_completed
                    
                    # Логируем для отладки
                    print(f"Сохранение студента {student_id}: {student_name}, статус на уроке: {status_on_lesson}, is_absent: {is_absent}")
                    
                    # Сохраняем связь
                    self.db.save_lesson_student(
                        lesson_id=lesson_id,
                        student_id=student_id,
                        status_on_lesson=status_on_lesson,
                        is_cancelled=is_cancelled,
                        is_paused=is_paused,
                        is_absent=is_absent,
                        is_rescheduled=is_rescheduled,
                        is_completed=is_completed_flag,
                        pause_info=pause_info,
                        extra_info=extra_info
                    )
        except Exception as e:
            print(f"Ошибка сохранения связей урока: {e}")
            import traceback
            traceback.print_exc()