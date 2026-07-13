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
import urllib.parse

from utils.text_format import *


class AlfaCRMApi:
    def __init__(self, config, crm_type='rts'):
        self.config = config
        self.crm_type = crm_type
        self.driver = None
        self.is_logged_in = False
        self.lock = threading.Lock()
        self.session = requests.Session()

        # Встроенные селекторы
        self.selectors = {
            'username': "#loginform-username",
            'password': "#loginform-password",
            'submit': "button[name='login-button']",
            'login_form': "#login-form",
            'csrf': "input[name='_csrf']",
            'login_success': ".navbar-top-links",
            'lesson_container': ".fc-time-grid-event",
            'time': ".fc-time",
            'client': ".fc-title",
            'status': ".fc-event",
            'link': "a.fc-event",
            'teacher': ".fc-title .ion-university",
            'schedule_url': "/teacher/1/calendar/index",
            'lesson_detail_url': "/teacher/1/calendar/fetch",
            'popover': ".popover"
        }

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
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.selectors['login_form']))
                )
                username_field = self.driver.find_element(By.CSS_SELECTOR, self.selectors['username'])
                password_field = self.driver.find_element(By.CSS_SELECTOR, self.selectors['password'])
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

                submit_button = self.driver.find_element(By.CSS_SELECTOR, self.selectors['submit'])
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

            time.sleep(2)

            for i in range(10):
                time.sleep(1)
                if self.check_login_success():
                    return True
                try:
                    error = self.driver.find_element(By.CSS_SELECTOR, ".alert-danger, .error-message")
                    if error.is_displayed():
                        print(f"Ошибка входа после 2FA: {error.text}")
                        return False
                except:
                    pass

                current_url = self.driver.current_url
                if 'login' not in current_url.lower():
                    return True

            return False

        except Exception as e:
            print(f"Ошибка ввода кода: {e}")
            return False

    def check_login_success(self):
        try:
            current_url = self.driver.current_url
            if 'login' not in current_url.lower():
                return True

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
            error = self.driver.find_element(By.CSS_SELECTOR, ".alert-danger, .error-message")
            return error.is_displayed()
        except:
            return False

    def get_lesson_popover_html(self, lesson_id):
        """Получает HTML поповера для урока по его ID"""
        try:
            # Ищем элемент урока на странице
            lesson_element = self.driver.find_element(By.CSS_SELECTOR, f"[data-id='{lesson_id}']")
            if not lesson_element:
                return None
            
            # Кликаем по уроку чтобы открыть поповер
            self.driver.execute_script("arguments[0].click();", lesson_element)
            time.sleep(0.5)
            
            # Ждем появления поповера
            try:
                popover = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.selectors['popover']))
                )
                return popover.get_attribute('outerHTML')
            except:
                return None
        except Exception as e:
            print(f"Ошибка получения поповера для урока {lesson_id}: {e}")
            return None

    def parse_popover_for_group(self, popover_html):
        """Парсит HTML поповера для получения ID и названия группы"""
        try:
            soup = BeautifulSoup(popover_html, 'html.parser')
            
            group_id = None
            group_name = None
            
            # Ищем блок с группами
            # <dt class="col-sm-5 text-muted">Группы</dt>
            # <dd class="col-sm-7 popover-description">
            #     <a href="/teacher/1/group/view?id=1406" target="_blank">ПП2.0 93</a>
            # </dd>
            
            dt_elements = soup.find_all('dt', class_='col-sm-5')
            for dt in dt_elements:
                if 'Группы' in dt.get_text():
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        link = dd.find('a', href=True)
                        if link:
                            href = link.get('href', '')
                            # Извлекаем ID из ссылки
                            id_match = re.search(r'group/view\?id=(\d+)', href)
                            if id_match:
                                group_id = id_match.group(1)
                                group_name = link.get_text(strip=True)
                                print(f"Парсинг поповера: найдена группа {group_name} с ID {group_id}")
                                break
            
            return group_id, group_name
        except Exception as e:
            print(f"Ошибка парсинга поповера: {e}")
            return None, None

    def get_lessons_from_api(self, start_date=None, end_date=None):
        if not self.is_logged_in:
            if not self.login():
                return []
        try:
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                self.session.cookies.set(cookie['name'], cookie['value'])
            try:
                csrf_token = self.driver.find_element(By.CSS_SELECTOR, self.selectors['csrf']).get_attribute('content')
            except:
                csrf_token = None
            if not start_date:
                start_date = datetime.now().strftime("%Y-%m-%d")
            if not end_date:
                end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            url = f"{self.config['site_url']}{self.selectors['lesson_detail_url']}"
            params = {'start': start_date, 'end': end_date, 'page': 1, 'with_groups': 1, 
                    'expand': 'group',
                    'include': 'group' 
                    }
            headers = {}
            if csrf_token:
                headers['X-CSRF-Token'] = csrf_token
            headers['X-Requested-With'] = 'XMLHttpRequest'
            headers['Referer'] = self.config['site_url'] + self.selectors['schedule_url']
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
            
            # Сначала загружаем страницу календаря для парсинга поповеров
            calendar_url = f"{self.config['site_url']}{self.selectors['schedule_url']}"
            self.driver.get(calendar_url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "fc-view-container"))
            )
            time.sleep(2)
            
            lessons = []
            for lesson_data in all_lessons:
                lesson = self.parse_api_lesson(lesson_data)
                if lesson:
                    # Если у урока нет group_id, пробуем получить из поповера
                    if not lesson.get('group_id') and lesson.get('id'):
                        lesson_id = lesson.get('id')
                        print(f"Пробуем получить группу для урока {lesson_id} через поповер...")
                        popover_html = self.get_lesson_popover_html(lesson_id)
                        if popover_html:
                            group_id, group_name = self.parse_popover_for_group(popover_html)
                            if group_id:
                                lesson['group_id'] = group_id
                                lesson['group_name'] = group_name
                                print(f"Получена группа из поповера: {group_name} (ID: {group_id})")
                                
                                # Обновляем группу в БД
                                if hasattr(self, 'db'):
                                    self.db.save_group(group_id, group_name, self.config['site_url'], self.crm_type)
                                    self.db.save_lesson_group(lesson_id, group_id)
                                    # Обновляем урок в БД
                                    self.db.save_lesson(lesson)
                    
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
            calendar_url = self.selectors['schedule_url']
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
            events = soup.select(self.selectors['lesson_container'])
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
            # Маппинг статусов
            status_map = {
                '1': 'scheduled',
                '2': 'cancelled',
                '3': 'completed',
                '4': 'rescheduled'
            }
            status = status_map.get(str(data.get('status')), 'scheduled')

            # Маппинг типов
            type_map = {
                '1': 'individual',
                '2': 'group',
                '3': 'trial',
                '4': 'tech_support',
                '5': 'trial'
            }
            lesson_type = type_map.get(str(data.get('type')), 'unknown')

            # Извлечение данных
            customers = data.get('customers', {})
            students = []
            customer_id = None

            # ========== ИЗВЛЕЧЕНИЕ ГРУППЫ ==========
            group_id = None
            group_name = None
            topic = data.get('subject', '')
            
            # 1. Пробуем получить group_id из данных
            if data.get('group_id'):
                group_id = str(data.get('group_id'))
            elif data.get('group'):
                group_id = str(data.get('group'))
            
            # 2. Пробуем получить group_name из title
            title = data.get('title', '')
            if title:
                group_match = re.match(r'^([^\(]+)', title)
                if group_match:
                    potential_name = group_match.group(1).strip()
                    if re.search(r'[А-ЯA-Z][А-ЯA-Z0-9. ]*\d+', potential_name):
                        group_name = potential_name
            
            # 3. Если не нашли в title, ищем в searchbuf
            if not group_name:
                searchbuf = data.get('searchbuf', '')
                search_match = re.search(r'([А-ЯA-Z][А-ЯA-Z0-9. ]*\d+)', searchbuf)
                if search_match:
                    group_name = search_match.group(1)
            
            # 4. Если есть group_name, ищем правильный ID в БД
            if group_name and hasattr(self, 'db'):
                # Ищем в БД по названию
                existing_group = self.db.get_group_by_name(group_name, self.crm_type)
                if existing_group:
                    group_id = existing_group.get('id')
                    print(f"Найдена группа в БД: {group_name} -> ID: {group_id}")
                else:
                    # Если группы нет в БД, пробуем получить через API
                    print(f"Группа {group_name} не найдена в БД, пробуем получить через API...")
                    groups = self.get_teacher_groups()
                    if group_name in groups:
                        group_id = groups[group_name]
                        # Сохраняем в БД
                        self.db.save_group(group_id, group_name, self.config['site_url'], self.crm_type)
                        print(f"Получена группа через API: {group_name} -> ID: {group_id}")
                    else:
                        # Создаем временный ID
                        import hashlib
                        group_id = hashlib.md5(group_name.encode()).hexdigest()[:10]
                        self.db.save_group(group_id, group_name, self.config['site_url'], self.crm_type)
                        print(f"Создан временный ID для группы: {group_id}")
            
            print(f"ИТОГО: group_id={group_id}, group_name={group_name}")

            # ========== ОБРАБОТКА УЧЕНИКОВ ==========
            if isinstance(customers, dict):
                for cid, name_html in customers.items():
                    clean_name = re.sub(r'<[^>]+>', '', name_html).strip()

                    is_cancelled = '<strike' in name_html
                    is_absent = 'text-muted' in name_html or 'не спис' in name_html.lower()
                    is_rescheduled = 'Перенос' in name_html or 'rescheduled' in name_html.lower()
                    pause_match = re.search(r'\(пауза\s+([^)]+)\)', name_html, re.IGNORECASE)
                    is_paused = bool(pause_match)
                    pause_info = pause_match.group(1) if pause_match else None
                    is_completed = status == 'completed'

                    balance_match = re.search(r'\((\d+)\s*(?:ост\.?|уроков?|осталось)\)', name_html, re.IGNORECASE)
                    balance = int(balance_match.group(1)) if balance_match else None

                    extra_match = re.search(r'\(([^)]*(?:ост\.?|уроков?|осталось)[^)]*)\)', name_html, re.IGNORECASE)
                    extra_info = extra_match.group(1) if extra_match else ''

                    if 'абон' in name_html.lower() or 'спис' in name_html.lower():
                        status_on_lesson = 'списывать'
                    elif 'не спис' in name_html.lower():
                        status_on_lesson = 'не списывать'
                    elif pause_info:
                        status_on_lesson = 'пауза'
                    else:
                        status_on_lesson = None

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
                        'status_on_lesson': status_on_lesson
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

            elif isinstance(customers, list):
                for item in customers:
                    if isinstance(item, dict):
                        cid = item.get('id')
                        name_html = item.get('name', '')
                        clean_name = re.sub(r'<[^>]+>', '', name_html).strip()

                        is_cancelled = '<strike' in name_html
                        is_absent = 'text-muted' in name_html or 'не спис' in name_html.lower()
                        is_rescheduled = 'Перенос' in name_html or 'rescheduled' in name_html.lower()
                        pause_match = re.search(r'\(пауза\s+([^)]+)\)', name_html, re.IGNORECASE)
                        is_paused = bool(pause_match)
                        pause_info = pause_match.group(1) if pause_match else None
                        is_completed = status == 'completed'

                        balance_match = re.search(r'\((\d+)\s*(?:ост\.?|уроков?|осталось)\)', name_html, re.IGNORECASE)
                        balance = int(balance_match.group(1)) if balance_match else None

                        extra_match = re.search(r'\(([^)]*(?:ост\.?|уроков?|осталось)[^)]*)\)', name_html, re.IGNORECASE)
                        extra_info = extra_match.group(1).strip() if extra_match else ''

                        if 'абон' in name_html.lower() or 'спис' in name_html.lower():
                            status_on_lesson = 'списывать'
                        elif 'не спис' in name_html.lower():
                            status_on_lesson = 'не списывать'
                        elif pause_info:
                            status_on_lesson = 'пауза'
                        else:
                            status_on_lesson = None

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
                            'status_on_lesson': status_on_lesson
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

            # Проверяем наличие темы
            if not topic:
                topic = data.get('title', '')
                if group_name and topic.startswith(group_name):
                    topic = topic.replace(group_name, '').strip()
                    topic = re.sub(r'\(\d+/\d+\)', '', topic).strip()

            lesson = {
                'id': str(data.get('id', f"{self.crm_type}_{datetime.now().timestamp()}")),
                'time': time_str,
                'client': ', '.join(client_names) if client_names else data.get('title', ''),
                'subject': data.get('subject', ''),
                'topic': topic,
                'comment': data.get('note', ''),
                'status': status,
                'link': f"{self.config['site_url']}{self.selectors['schedule_url']}?date={data.get('date', '')}",
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
            printd(element)
            time_elem = element.select_one(self.selectors['time'].replace('.', ''))
            time_text = time_elem.text.strip() if time_elem else ''
            time_match = re.search(r'(\d{1,2}:\d{2})', time_text)
            time_str = time_match.group(1) if time_match else ''
            title_elem = element.select_one(self.selectors['client'].replace('.', ''))
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

            group_id = None
            group_name = None
            link_elem = element.select_one('a')
            if link_elem:
                href = link_elem.get('href', '')
                if 'group/view' in href:
                    gid_match = re.search(r'id=(\d+)', href)
                    if gid_match:
                        group_id = gid_match.group(1)
                        name_match = re.search(r'name=([^&]+)', href)
                        if name_match:
                            group_name = name_match.group(1)

            lesson = {
                'id': lesson_id,
                'time': time_str,
                'client': client,
                'subject': '',
                'topic': '',
                'comment': '',
                'status': status,
                'link': self.config['site_url'] + self.selectors['schedule_url'],
                'teacher': teacher,
                'room': room,
                'type': lesson_type,
                'is_occupied': status in ['scheduled', 'completed'],
                'date': date or datetime.now().strftime("%Y-%m-%d"),
                'timestamp': datetime.now().isoformat(),
                'group_id': group_id,
                'group_name': group_name,
                'students': []
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

    def save_lesson_relations(self, lesson, students, group_id=None):
        """Сохраняет связи урока с учениками и группами"""
        try:
            lesson_id = lesson.get('id')
            crm_type = lesson.get('crm_type')
            site_url = lesson.get('site_url')
            lesson_status = lesson.get('status')
            is_completed = lesson_status == 'completed'

            if not group_id:
                group_id = lesson.get('group_id')

            # Сохраняем группу если есть ID
            if group_id and hasattr(self, 'db'):
                # Проверяем, есть ли группа в БД
                existing = self.db.get_group(group_id)
                if not existing:
                    # Если нет - создаем с временным названием
                    group_name = f"Группа #{group_id}"
                    self.db.save_group(group_id, group_name, site_url, crm_type)
                
                # Сохраняем связь урока с группой
                self.db.save_lesson_group(lesson_id, group_id)

            # Сохраняем учеников и связи
            for student in students:
                student_id = student.get('id')
                student_name = student.get('name', '')

                if student_id and hasattr(self, 'db'):
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

                    status_on_lesson = student.get('status_on_lesson')
                    extra_info = student.get('extra_info', '')
                    pause_info = student.get('pause_info', '')

                    if not status_on_lesson:
                        if pause_info:
                            status_on_lesson = 'пауза'
                        elif 'абон' in extra_info.lower() or 'спис' in extra_info.lower():
                            status_on_lesson = 'списывать'
                        elif 'не спис' in extra_info.lower():
                            status_on_lesson = 'не списывать'

                    is_cancelled = student.get('is_cancelled', False)
                    is_paused = student.get('is_paused', False)
                    is_absent = student.get('is_absent', False)
                    is_rescheduled = student.get('is_rescheduled', False)
                    is_completed_flag = is_completed

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
            
    def get_teacher_groups(self):
        """
        Получает все группы учителя из API.
        Возвращает словарь {group_name: group_id}
        """
        try:
            # Пробуем разные возможные эндпоинты
            endpoints = [
                f"{self.config['site_url']}/teacher/1/group/index",
                f"{self.config['site_url']}/teacher/1/group/list",
                f"{self.config['site_url']}/teacher/1/group/fetch",
                f"{self.config['site_url']}/teacher/1/group/get-groups",
            ]
            
            # Получаем CSRF токен если нужен
            try:
                csrf_token = self.driver.find_element(By.CSS_SELECTOR, self.selectors['csrf']).get_attribute('content')
            except:
                csrf_token = None
            
            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': f"{self.config['site_url']}/teacher/1/group/index"
            }
            if csrf_token:
                headers['X-CSRF-Token'] = csrf_token
            
            groups = {}
            
            for url in endpoints:
                try:
                    print(f"Пробуем получить группы по URL: {url}")
                    response = self.session.get(url, headers=headers)
                    
                    if response.status_code == 200:
                        # Пробуем распарсить JSON
                        try:
                            data = response.json()
                            print(f"Получен JSON: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                            
                            # Парсим JSON в зависимости от структуры
                            if isinstance(data, dict):
                                # Ищем ключи, которые могут содержать группы
                                possible_keys = ['groups', 'collection', 'items', 'data', 'result']
                                for key in possible_keys:
                                    if key in data and isinstance(data[key], list):
                                        for item in data[key]:
                                            if 'id' in item and ('name' in item or 'title' in item):
                                                group_id = str(item.get('id'))
                                                group_name = item.get('name') or item.get('title', '')
                                                groups[group_name] = group_id
                                                print(f"Найдена группа: {group_name} -> ID: {group_id}")
                                        break
                                
                                # Если не нашли в списке, может быть словарь с группами
                                if not groups:
                                    for key, value in data.items():
                                        if isinstance(value, dict) and 'id' in value and 'name' in value:
                                            groups[value['name']] = str(value['id'])
                                        elif isinstance(value, list) and len(value) > 0:
                                            for item in value:
                                                if isinstance(item, dict) and 'id' in item and ('name' in item or 'title' in item):
                                                    group_name = item.get('name') or item.get('title', '')
                                                    groups[group_name] = str(item.get('id'))
                            
                            elif isinstance(data, list):
                                for item in data:
                                    if isinstance(item, dict) and 'id' in item and ('name' in item or 'title' in item):
                                        group_name = item.get('name') or item.get('title', '')
                                        groups[group_name] = str(item.get('id'))
                            
                            # Если нашли группы - выходим
                            if groups:
                                print(f"Найдено {len(groups)} групп через API")
                                break
                                
                        except ValueError:
                            # Если не JSON, пробуем парсить HTML
                            print("Ответ не в JSON формате, пробуем парсить HTML...")
                            soup = BeautifulSoup(response.text, 'html.parser')
                            
                            # Ищем ссылки на группы в HTML
                            for link in soup.select('a[href*="group/view"]'):
                                href = link.get('href')
                                match = re.search(r'id=(\d+)', href)
                                if match:
                                    group_id = match.group(1)
                                    group_name = link.text.strip()
                                    if group_name:
                                        groups[group_name] = group_id
                                        print(f"Найдена группа (HTML): {group_name} -> ID: {group_id}")
                            
                            if groups:
                                break
                            
                except Exception as e:
                    print(f"Ошибка при запросе к {url}: {e}")
                    continue
            
            # Сохраняем группы в БД
            if groups and hasattr(self, 'db'):
                for group_name, group_id in groups.items():
                    self.db.save_group(
                        group_id=group_id,
                        name=group_name,
                        site_url=self.config['site_url'],
                        crm_type=self.crm_type
                    )
                print(f"Сохранено {len(groups)} групп в БД")
            
            return groups
            
        except Exception as e:
            print(f"Ошибка получения групп: {e}")
            import traceback
            traceback.print_exc()
            return {}