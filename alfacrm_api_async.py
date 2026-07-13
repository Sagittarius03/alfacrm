# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import time
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import threading
import hashlib

from utils.text_format import *


class AlfaCRMApiAsync:
    """Асинхронная версия API для работы с AlfaCRM"""
    
    def __init__(self, config: Dict[str, Any], crm_type: str = 'rts'):
        self.config = config
        self.crm_type = crm_type
        self.driver = None
        self.is_logged_in = False
        self.lock = threading.Lock()
        self.session = None  # aiohttp session
        
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
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Закрытие сессии"""
        if self.session:
            await self.session.close()
        self.close_driver()
    
    def setup_driver(self):
        """Настройка Selenium драйвера (синхронно)"""
        if self.driver:
            return
        
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
    
    def close_driver(self):
        """Закрывает драйвер"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            self.is_logged_in = False
    
    async def login(self, db) -> bool:
        """Асинхронный вход в систему"""
        with self.lock:
            if self.is_logged_in:
                return True
            
            try:
                # Пробуем восстановить сессию
                saved_cookies = await db.get_session_cookies(self.crm_type) if db else []
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
                            clean_cookie = {k: v for k, v in cookie.items() 
                                          if k in ['name', 'value', 'domain', 'path', 'expiry', 'httpOnly', 'secure']}
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
                
                # Обычный логин
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
                
                if self.is_logged_in and db:
                    cookies = self.driver.get_cookies()
                    await db.save_session_cookies(cookies, self.crm_type)
                    print(f"Сессия сохранена для {self.crm_type}")
                
                return self.is_logged_in
                
            except Exception as e:
                print(f"Ошибка при входе для {self.crm_type}: {e}")
                return False
    
    def check_2fa_required(self) -> bool:
        """Проверяет, требуется ли 2FA"""
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
    
    def get_verification_code(self) -> Optional[str]:
        """Получает код подтверждения из почты"""
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
    
    def enter_2fa_code(self, code: str) -> bool:
        """Вводит код 2FA"""
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
    
    def check_login_success(self) -> bool:
        """Проверяет успешность входа"""
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
    
    def get_lesson_popover_html(self, lesson_id: str) -> Optional[str]:
        """Получает HTML поповера для урока (синхронно)"""
        try:
            if not self.driver:
                self.setup_driver()
            
            # Ищем элемент урока на странице
            lesson_element = self.driver.find_element(By.CSS_SELECTOR, f"[data-id='{lesson_id}']")
            if not lesson_element:
                return None
            
            # Кликаем по уроку чтобы открыть поповер
            self.driver.execute_script("arguments[0].click();", lesson_element)
            time.sleep(0.8)
            
            # Ждем появления поповера
            try:
                popover = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".popover"))
                )
                return popover.get_attribute('outerHTML')
            except:
                return None
        except Exception as e:
            print(f"Ошибка получения поповера для урока {lesson_id}: {e}")
            return None
    
    def parse_popover_for_students(self, popover_html: str) -> Dict[str, Dict]:
        """Парсит HTML поповера для получения статусов учеников"""
        try:
            soup = BeautifulSoup(popover_html, 'html.parser')
            students_data = {}
            
            # Ищем все ссылки на учеников в поповере
            rows = soup.find_all('div', class_='row')
            
            for row in rows:
                col = row.find('div', class_='col-sm-12')
                if not col:
                    continue
                
                links = col.find_all('a', href=True)
                
                for link in links:
                    href = link.get('href', '')
                    if 'customer/view' not in href:
                        continue
                    
                    id_match = re.search(r'id=(\d+)', href)
                    if not id_match:
                        continue
                    student_id = id_match.group(1)
                    link_html = str(link)
                    
                    # Извлекаем имя
                    name_span = link.find('span', class_='customer-name')
                    if name_span:
                        student_name = name_span.get_text(strip=True)
                    else:
                        student_name = link.get_text(strip=True)
                    
                    # Определяем статусы
                    is_cancelled = '<strike' in link_html or 'strike' in link_html
                    is_absent = 'text-muted' in link_html
                    
                    # Проверяем на паузу
                    pause_match = re.search(r'\(пауза\s+([^)]+)\)', link_html, re.IGNORECASE)
                    is_paused = bool(pause_match)
                    pause_info = pause_match.group(1) if pause_match else None
                    
                    # Определяем статус списания
                    status_on_lesson = None
                    if 'абон' in link_html.lower():
                        status_on_lesson = 'списывать'
                    elif 'спис' in link_html.lower() and 'не спис' not in link_html.lower():
                        status_on_lesson = 'списывать'
                    elif 'не спис' in link_html.lower():
                        status_on_lesson = 'не списывать'
                    elif pause_info:
                        status_on_lesson = 'пауза'
                    
                    # Извлекаем остаток
                    balance_match = re.search(r'\((\d+)\s*(?:ост\.?|уроков?|осталось)\)', link_html, re.IGNORECASE)
                    balance = int(balance_match.group(1)) if balance_match else None
                    
                    # Дополнительная информация
                    extra_match = re.search(r'\(([^)]*(?:ост\.?|уроков?|осталось)[^)]*)\)', link_html, re.IGNORECASE)
                    extra_info = extra_match.group(1) if extra_match else ''
                    
                    students_data[student_id] = {
                        'id': student_id,
                        'name': student_name,
                        'is_cancelled': is_cancelled,
                        'is_paused': is_paused,
                        'pause_info': pause_info,
                        'extra_info': extra_info,
                        'balance': balance,
                        'is_rescheduled': False,
                        'is_absent': is_absent,
                        'status_on_lesson': status_on_lesson
                    }
            
            return students_data
            
        except Exception as e:
            print(f"Ошибка парсинга поповера: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    async def get_lessons_from_api(self, db, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Асинхронно получает уроки через API"""
        if not self.is_logged_in:
            if not await self.login(db):
                return []
        
        try:
            # Получаем cookies из драйвера
            cookies = self.driver.get_cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}
            
            # Получаем CSRF токен
            try:
                csrf_token = self.driver.find_element(By.CSS_SELECTOR, self.selectors['csrf']).get_attribute('content')
            except:
                csrf_token = None
            
            if not start_date:
                start_date = datetime.now().strftime("%Y-%m-%d")
            if not end_date:
                end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            
            url = f"{self.config['site_url']}{self.selectors['lesson_detail_url']}"
            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': f"{self.config['site_url']}{self.selectors['schedule_url']}"
            }
            if csrf_token:
                headers['X-CSRF-Token'] = csrf_token
            
            all_lessons = []
            page = 1
            total = None
            
            async with aiohttp.ClientSession(cookies=cookie_dict) as session:
                while True:
                    params = {'start': start_date, 'end': end_date, 'page': page}
                    
                    async with session.get(url, params=params, headers=headers) as response:
                        if response.status != 200:
                            break
                        data = await response.json()
                        
                        if total is None:
                            total = data.get('total', 0)
                        lessons_data = data.get('collection', [])
                        all_lessons.extend(lessons_data)
                        
                        if len(all_lessons) >= total or not lessons_data:
                            break
                        page += 1
            
            # Загружаем страницу календаря для парсинга поповеров
            calendar_url = f"{self.config['site_url']}{self.selectors['schedule_url']}"
            self.driver.get(calendar_url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "fc-view-container"))
            )
            time.sleep(2)
            
            lessons = []
            for lesson_data in all_lessons:
                lesson = self.parse_api_lesson(lesson_data, db)
                if lesson:
                    lesson_id = lesson.get('id')
                    
                    # Получаем данные из поповера (синхронно)
                    popover_html = self.get_lesson_popover_html(lesson_id)
                    if popover_html:
                        popover_data = self.parse_popover_for_students(popover_html)
                        if popover_data:
                            # Обновляем статусы учеников из поповера
                            updated_students = []
                            for student in lesson.get('students', []):
                                student_id = student.get('id')
                                if student_id and student_id in popover_data:
                                    popover_student = popover_data[student_id]
                                    student['status_on_lesson'] = popover_student.get('status_on_lesson')
                                    student['is_absent'] = popover_student.get('is_absent', False)
                                    student['is_paused'] = popover_student.get('is_paused', False)
                                    student['pause_info'] = popover_student.get('pause_info')
                                    student['extra_info'] = popover_student.get('extra_info', '')
                                    student['balance'] = popover_student.get('balance')
                                    student['is_cancelled'] = popover_student.get('is_cancelled', False)
                                    student['is_rescheduled'] = popover_student.get('is_rescheduled', False)
                                updated_students.append(student)
                            lesson['students'] = updated_students
                    
                    # Сохраняем урок и связи в БД
                    if db:
                        await self.save_lesson_relations(lesson, lesson.get('students', []), lesson.get('group_id'), db)
                    
                    lessons.append(lesson)
            
            print(f"Найдено {len(lessons)} уроков через API для {self.crm_type}")
            return lessons
            
        except Exception as e:
            print(f"Ошибка получения уроков через API для {self.crm_type}: {e}")
            import traceback
            traceback.print_exc()
            return await self.get_lessons_from_page(db, start_date, end_date)
    
    async def get_lessons_from_page(self, db, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Получает уроки через парсинг страницы (резервный метод)"""
        if not self.is_logged_in:
            if not await self.login(db):
                return []
        
        try:
            if not start_date:
                start_date = datetime.now().strftime("%Y-%m-%d")
            
            if not self.driver:
                self.setup_driver()
            
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
    
    def parse_api_lesson(self, data: Dict, db=None) -> Optional[Dict]:
        """Парсит урок из JSON"""
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
            if group_name and db:
                # Ищем в БД по названию
                existing_group = db.get_group_by_name(group_name, self.crm_type)
                if existing_group:
                    group_id = existing_group.get('id')
                    print(f"Найдена группа в БД по названию: {group_name} -> ID: {group_id}")
                else:
                    # Если нет в БД, создаем временный ID
                    print(f"Группа {group_name} не найдена в БД")
                    import hashlib
                    group_id = hashlib.md5(group_name.encode()).hexdigest()[:10]
                    # Сохраняем группу в БД
                    db.save_group(group_id, group_name, self.config['site_url'], self.crm_type)
                    print(f"Создана группа в БД: {group_name} -> ID: {group_id}")
            
            print(f"ИТОГО: group_id={group_id}, group_name={group_name}")
            
            # ========== ОБРАБОТКА УЧЕНИКОВ ==========
            if isinstance(customers, dict):
                for cid, name_html in customers.items():
                    clean_name = re.sub(r'<[^>]+>', '', name_html).strip()
                    
                    is_cancelled = '<strike' in name_html
                    is_absent = 'text-muted' in name_html
                    is_rescheduled = 'Перенос' in name_html or 'rescheduled' in name_html.lower()
                    pause_match = re.search(r'\(пауза\s+([^)]+)\)', name_html, re.IGNORECASE)
                    is_paused = bool(pause_match)
                    pause_info = pause_match.group(1) if pause_match else None
                    is_completed = status == 'completed'
                    
                    balance_match = re.search(r'\((\d+)\s*(?:ост\.?|уроков?|осталось)\)', name_html, re.IGNORECASE)
                    balance = int(balance_match.group(1)) if balance_match else None
                    
                    extra_match = re.search(r'\(([^)]*(?:ост\.?|уроков?|осталось)[^)]*)\)', name_html, re.IGNORECASE)
                    extra_info = extra_match.group(1) if extra_match else ''
                    
                    status_on_lesson = None
                    if 'абон' in name_html.lower():
                        status_on_lesson = 'списывать'
                    elif 'не спис' in name_html.lower():
                        status_on_lesson = 'не списывать'
                    elif pause_info:
                        status_on_lesson = 'пауза'
                    
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
                    
                    if not customer_id:
                        customer_id = cid
            
            elif isinstance(customers, list):
                for item in customers:
                    if isinstance(item, dict):
                        cid = item.get('id')
                        name_html = item.get('name', '')
                        clean_name = re.sub(r'<[^>]+>', '', name_html).strip()
                        
                        is_cancelled = '<strike' in name_html
                        is_absent = 'text-muted' in name_html
                        is_rescheduled = 'Перенос' in name_html or 'rescheduled' in name_html.lower()
                        pause_match = re.search(r'\(пауза\s+([^)]+)\)', name_html, re.IGNORECASE)
                        is_paused = bool(pause_match)
                        pause_info = pause_match.group(1) if pause_match else None
                        is_completed = status == 'completed'
                        
                        balance_match = re.search(r'\((\d+)\s*(?:ост\.?|уроков?|осталось)\)', name_html, re.IGNORECASE)
                        balance = int(balance_match.group(1)) if balance_match else None
                        
                        extra_match = re.search(r'\(([^)]*(?:ост\.?|уроков?|осталось)[^)]*)\)', name_html, re.IGNORECASE)
                        extra_info = extra_match.group(1).strip() if extra_match else ''
                        
                        status_on_lesson = None
                        if 'абон' in name_html.lower():
                            status_on_lesson = 'списывать'
                        elif 'не спис' in name_html.lower():
                            status_on_lesson = 'не списывать'
                        elif pause_info:
                            status_on_lesson = 'пауза'
                        
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
                'group_id': group_id
            }
            
            return lesson
            
        except Exception as e:
            print(f"Ошибка парсинга API урока: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def parse_page_lesson(self, element, date: str) -> Optional[Dict]:
        """Парсит урок из HTML страницы"""
        try:
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
            
            return {
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
                'students': []
            }
            
        except Exception as e:
            print(f"Ошибка парсинга страницы урока: {e}")
            return None
    
    async def get_teacher_groups(self, db) -> Dict[str, str]:
        """Асинхронно получает все группы учителя с реальными ID из API"""
        try:
            if not self.is_logged_in:
                if not await self.login(db):
                    return {}
            
            # Пробуем разные возможные эндпоинты
            endpoints = [
                f"{self.config['site_url']}/teacher/1/group/index",
                f"{self.config['site_url']}/teacher/1/group/list",
                f"{self.config['site_url']}/teacher/1/group/fetch",
                f"{self.config['site_url']}/teacher/1/group/get-groups",
                f"{self.config['site_url']}/teacher/1/group/json",
            ]
            
            # Получаем CSRF токен
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
            
            # Получаем cookies из драйвера
            cookies = self.driver.get_cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}
            
            groups = {}
            
            async with aiohttp.ClientSession(cookies=cookie_dict) as session:
                for url in endpoints:
                    try:
                        print(f"Пробуем получить группы по URL: {url}")
                        async with session.get(url, headers=headers) as response:
                            if response.status != 200:
                                continue
                            
                            try:
                                data = await response.json()
                                print(f"Получен JSON: {type(data)}")
                                
                                # Парсим JSON в зависимости от структуры
                                if isinstance(data, dict):
                                    # Ищем ключи, которые могут содержать группы
                                    possible_keys = ['groups', 'collection', 'items', 'data', 'result', 'list']
                                    for key in possible_keys:
                                        if key in data and isinstance(data[key], list):
                                            for item in data[key]:
                                                if 'id' in item and ('name' in item or 'title' in item):
                                                    group_id = str(item.get('id'))
                                                    group_name = item.get('name') or item.get('title', '')
                                                    if group_name and group_id:
                                                        groups[group_name] = group_id
                                                        print(f"Найдена группа: {group_name} -> ID: {group_id}")
                                            break
                                    
                                    # Если не нашли в списке, может быть словарь с группами
                                    if not groups:
                                        for key, value in data.items():
                                            if isinstance(value, dict) and 'id' in value and ('name' in value or 'title' in value):
                                                group_id = str(value.get('id'))
                                                group_name = value.get('name') or value.get('title', '')
                                                if group_name and group_id:
                                                    groups[group_name] = group_id
                                                    print(f"Найдена группа (dict): {group_name} -> ID: {group_id}")
                                            elif isinstance(value, list) and len(value) > 0:
                                                for item in value:
                                                    if isinstance(item, dict) and 'id' in item and ('name' in item or 'title' in item):
                                                        group_id = str(item.get('id'))
                                                        group_name = item.get('name') or item.get('title', '')
                                                        if group_name and group_id:
                                                            groups[group_name] = group_id
                                                            print(f"Найдена группа (list): {group_name} -> ID: {group_id}")
                                
                                elif isinstance(data, list):
                                    for item in data:
                                        if isinstance(item, dict) and 'id' in item and ('name' in item or 'title' in item):
                                            group_id = str(item.get('id'))
                                            group_name = item.get('name') or item.get('title', '')
                                            if group_name and group_id:
                                                groups[group_name] = group_id
                                                print(f"Найдена группа (list root): {group_name} -> ID: {group_id}")
                                
                                # Если нашли группы - сохраняем и выходим
                                if groups:
                                    print(f"Найдено {len(groups)} групп через API")
                                    break
                                    
                            except ValueError as e:
                                print(f"Ответ не в JSON формате: {e}")
                                # Если не JSON, пробуем парсить HTML
                                soup = BeautifulSoup(response.text, 'html.parser')
                                
                                # Ищем ссылки на группы в HTML
                                for link in soup.select('a[href*="group/view"]'):
                                    href = link.get('href')
                                    match = re.search(r'id=(\d+)', href)
                                    if match:
                                        group_id = match.group(1)
                                        group_name = link.text.strip()
                                        if group_name and group_id:
                                            groups[group_name] = group_id
                                            print(f"Найдена группа (HTML): {group_name} -> ID: {group_id}")
                                
                                if groups:
                                    break
                            
                    except Exception as e:
                        print(f"Ошибка при запросе к {url}: {e}")
                        continue
            
            # Сохраняем группы в БД с реальными ID
            if groups and db:
                for group_name, group_id in groups.items():
                    # Проверяем, есть ли уже группа с таким ID
                    existing = await db.get_group(group_id)
                    if not existing:
                        await db.save_group(
                            group_id=group_id,
                            name=group_name,
                            site_url=self.config['site_url'],
                            crm_type=self.crm_type
                        )
                        print(f"Сохранена группа: {group_name} -> ID: {group_id}")
                    else:
                        # Обновляем название если изменилось
                        if existing.get('name') != group_name:
                            await db.save_group(
                                group_id=group_id,
                                name=group_name,
                                site_url=self.config['site_url'],
                                crm_type=self.crm_type
                            )
                            print(f"Обновлена группа: {group_name} -> ID: {group_id}")
                
                print(f"Сохранено {len(groups)} групп в БД")
            
            return groups
            
        except Exception as e:
            print(f"Ошибка получения групп: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    async def save_lesson_relations(self, lesson: Dict, students: List[Dict], group_id: str, db):
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
            if group_id and db:
                existing = await db.get_group(group_id)
                if not existing:
                    # Пробуем найти группу по названию в БД
                    group_name = None
                    for student in students:
                        if student.get('group_name'):
                            group_name = student.get('group_name')
                            break
                    if not group_name:
                        group_name = f"Группа #{group_id}"
                    await db.save_group(group_id, group_name, site_url, crm_type)
                await db.save_lesson_group(lesson_id, group_id)
            
            # Сохраняем учеников и связи
            for student in students:
                student_id = student.get('id')
                student_name = student.get('name', '')
                
                if student_id and db:
                    balance = student.get('balance')
                    student_status = 'active'
                    if student.get('is_paused'):
                        student_status = 'paused'
                    elif student.get('is_cancelled'):
                        student_status = 'cancelled'
                    
                    await db.save_student(
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
                    
                    await db.save_lesson_student(
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
            
            # Сохраняем сам урок в БД
            if db:
                await db.save_lesson(lesson)
                print(f"Сохранен урок {lesson_id} с {len(students)} учениками")
                    
        except Exception as e:
            print(f"Ошибка сохранения связей урока: {e}")
            import traceback
            traceback.print_exc()