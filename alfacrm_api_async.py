# -*- coding: utf-8 -*-
import asyncio
import time
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page
import threading
import hashlib
import requests
import imaplib
import email


class AlfaCRMApiAsync:
    """API для работы с AlfaCRM через Playwright"""
    
    def __init__(self, config: Dict[str, Any], crm_type: str = 'rts'):
        self.config = config
        self.crm_type = crm_type
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.is_logged_in = False
        self.lock = threading.Lock()
        self.db = None
        self._playwright = None
        self._2fa_code = None
        self._2fa_event = threading.Event()
        self._2fa_required = False
        self._login_attempts = 0
        
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
            'popover': ".popover",
        }
    
    def set_2fa_code(self, code: str):
        """Устанавливает код 2FA и сигнализирует о готовности"""
        self._2fa_code = code
        self._2fa_event.set()
    
    def is_2fa_required(self) -> bool:
        """Проверяет, требуется ли 2FA"""
        return self._2fa_required
    
    async def __aenter__(self):
        await self._init_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_async()
    
    async def _init_browser(self):
        """Инициализация браузера"""
        if self.browser:
            return
        
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1920,1080',
            ]
        )
        self.page = await self.browser.new_page(
            viewport={'width': 1920, 'height': 1080}
        )
        print(f"✅ Браузер инициализирован для {self.crm_type}")
    
    async def close_async(self):
        """Асинхронное закрытие браузера"""
        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
            self.browser = None
            self.page = None
            self.is_logged_in = False
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except:
                pass
            self._playwright = None
    
    def close_sync(self):
        """Синхронное закрытие браузера"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.close_async())
            finally:
                loop.close()
        except Exception as e:
            print(f"Ошибка закрытия браузера: {e}")
            if self.browser:
                try:
                    self.browser.close()
                except:
                    pass
                self.browser = None
                self.page = None
                self.is_logged_in = False
            
            if self._playwright:
                try:
                    self._playwright.stop()
                except:
                    pass
                self._playwright = None
    
    def close(self):
        """Закрытие браузера (синхронно)"""
        self.close_sync()
    
    async def check_2fa_required(self) -> bool:
        """Проверяет, требуется ли 2FA"""
        try:
            if not self.page:
                return False
                
            current_url = self.page.url
            if '2fa' in current_url.lower() or 'verification' in current_url.lower():
                self._2fa_required = True
                return True
            
            code_selectors = [
                "#login2faform-code",
                "#loginform-verificationcode",
                "input[name='code']",
                "input[name='Login2FAForm[code]']",
                "input[name='LoginForm[verificationcode]']"
            ]
            for selector in code_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element and await element.is_visible():
                        self._2fa_required = True
                        return True
                except:
                    continue
            
            try:
                content = await self.page.content()
                if re.search(r'код подтверждения|verification code|2fa|two-factor', content, re.IGNORECASE):
                    self._2fa_required = True
                    return True
            except:
                pass
            
            self._2fa_required = False
            return False
        except Exception as e:
            print(f"Ошибка проверки 2FA: {e}")
            self._2fa_required = False
            return False
    
    async def enter_2fa_code(self, code: str) -> bool:
        """Вводит код 2FA"""
        try:
            if not self.page:
                return False
                
            code_selectors = [
                "#login2faform-code",
                "#loginform-verificationcode",
                "input[name='code']",
                "input[name='Login2FAForm[code]']",
                "input[name='LoginForm[verificationcode]']"
            ]
            
            code_field = None
            for selector in code_selectors:
                try:
                    code_field = await self.page.wait_for_selector(selector, timeout=3000)
                    if code_field:
                        break
                except:
                    continue
            
            if not code_field:
                print("❌ Не найдено поле для ввода кода")
                return False
            
            await code_field.fill(code)
            await asyncio.sleep(0.5)
            
            submit_selectors = [
                "button[type='submit']",
                "button[name='login-button']",
                "text=Войти",
                "text=Log in",
                "text=Подтвердить",
                "text=Confirm"
            ]
            
            clicked = False
            for selector in submit_selectors:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click()
                        clicked = True
                        break
                except:
                    continue
            
            if not clicked:
                await code_field.press("Enter")
            
            await asyncio.sleep(3)
            
            if await self.check_login_success():
                return True
            
            try:
                error = await self.page.query_selector(".alert-danger, .error-message")
                if error:
                    error_text = await error.text_content()
                    print(f"❌ Ошибка входа после 2FA: {error_text}")
            except:
                pass
            
            return False
            
        except Exception as e:
            print(f"Ошибка ввода кода 2FA: {e}")
            return False
    
    async def check_login_success(self) -> bool:
        """Проверяет успешность входа"""
        try:
            if not self.page:
                return False
                
            current_url = self.page.url
            if 'login' not in current_url.lower() and '2fa' not in current_url.lower():
                return True
            
            selectors = [
                ".navbar-top-links",
                ".profile-link",
                "#side-menu",
                ".user-menu",
                ".logout",
                ".header-user",
                ".avatar"
            ]
            for selector in selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element and await element.is_visible():
                        return True
                except:
                    continue
            
            return False
        except Exception as e:
            return False
    
    async def login_async(self) -> bool:
        """Асинхронный вход в систему"""
        with self.lock:
            if self.is_logged_in:
                return True
            
            try:
                if not self.browser:
                    await self._init_browser()
                
                # Пробуем восстановить сессию
                saved_cookies = self.db.get_session_cookies(self.crm_type) if self.db else []
                if saved_cookies:
                    print(f"🔄 Попытка восстановления сессии для {self.crm_type}...")
                    await self.page.goto(self.config['site_url'])
                    
                    playwright_cookies = []
                    for cookie in saved_cookies:
                        if cookie.get('domain'):
                            playwright_cookies.append({
                                'name': cookie.get('name', ''),
                                'value': cookie.get('value', ''),
                                'domain': cookie.get('domain', ''),
                                'path': cookie.get('path', '/'),
                                'expires': cookie.get('expiry'),
                                'httpOnly': cookie.get('httpOnly', False),
                                'secure': cookie.get('secure', False),
                            })
                    
                    if playwright_cookies:
                        await self.page.context.add_cookies(playwright_cookies)
                        await self.page.reload()
                        await asyncio.sleep(2)
                        
                        if await self.check_login_success():
                            self.is_logged_in = True
                            print(f"✅ Сессия восстановлена для {self.crm_type}")
                            return True
                
                # Обычный логин
                print(f"🔑 Логин на {self.config['site_url']} ({self.crm_type})")
                await self.page.goto(self.config['site_url'])
                
                try:
                    await self.page.wait_for_selector(self.selectors['login_form'], timeout=15000)
                except:
                    if await self.check_login_success():
                        self.is_logged_in = True
                        return True
                    print("❌ Не найдена форма входа")
                    return False
                
                try:
                    await self.page.fill(self.selectors['username'], self.config['username'])
                    await self.page.fill(self.selectors['password'], self.config['password'])
                except Exception as e:
                    print(f"❌ Ошибка заполнения формы: {e}")
                    return False
                
                try:
                    await self.page.check("#loginform-rememberme")
                except:
                    pass
                
                await self.page.click(self.selectors['submit'])
                await asyncio.sleep(3)
                
                # Проверяем 2FA
                if await self.check_2fa_required():
                    print(f"🔐 ТРЕБУЕТСЯ КОД ПОДТВЕРЖДЕНИЯ для {self.crm_type}")
                    self._2fa_required = True
                    return False
                else:
                    if await self.check_login_success():
                        self.is_logged_in = True
                        print(f"✅ Успешный вход для {self.crm_type}")
                        if self.db:
                            cookies = await self.page.context.cookies()
                            self.db.save_session_cookies(cookies, self.crm_type)
                            print(f"💾 Сессия сохранена для {self.crm_type}")
                        return True
                    else:
                        try:
                            error = await self.page.query_selector(".alert-danger")
                            if error:
                                error_text = await error.text_content()
                                print(f"❌ Ошибка входа: {error_text}")
                        except:
                            pass
                        return False
                
            except Exception as e:
                print(f"❌ Ошибка при входе для {self.crm_type}: {e}")
                import traceback
                traceback.print_exc()
                return False
    
    async def continue_login_with_2fa(self, code: str) -> bool:
        """Продолжает вход с кодом 2FA"""
        try:
            if await self.enter_2fa_code(code):
                self.is_logged_in = True
                print(f"✅ Успешный вход с 2FA для {self.crm_type}")
                if self.db:
                    cookies = await self.page.context.cookies()
                    self.db.save_session_cookies(cookies, self.crm_type)
                    print(f"💾 Сессия сохранена для {self.crm_type}")
                return True
            else:
                print(f"❌ Ошибка ввода кода для {self.crm_type}")
                return False
        except Exception as e:
            print(f"❌ Ошибка при входе с 2FA: {e}")
            return False
    
    def login_sync(self) -> bool:
        """Синхронный вход"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.login_async())
        finally:
            loop.close()
    
    def login(self) -> bool:
        """Синхронный вызов (для совместимости)"""
        return self.login_sync()
    
    # ========== ОСТАЛЬНЫЕ МЕТОДЫ ==========
    
    async def get_teacher_groups_async(self) -> Dict[str, str]:
        """Асинхронное получение групп"""
        try:
            if not self.is_logged_in:
                if not await self.login_async():
                    return {}
            
            if not self.page:
                return {}
            
            cookies = await self.page.context.cookies()
            
            csrf_token = None
            try:
                csrf_input = await self.page.query_selector(self.selectors['csrf'])
                if csrf_input:
                    csrf_token = await csrf_input.get_attribute('content')
            except:
                pass
            
            endpoints = [
                f"{self.config['site_url']}/teacher/1/group/index",
                f"{self.config['site_url']}/teacher/1/group/list",
                f"{self.config['site_url']}/teacher/1/group/fetch",
                f"{self.config['site_url']}/teacher/1/group/get-groups",
            ]
            
            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': f"{self.config['site_url']}/teacher/1/group/index"
            }
            if csrf_token:
                headers['X-CSRF-Token'] = csrf_token
            
            groups = {}
            session = requests.Session()
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'])
            
            for url in endpoints:
                try:
                    response = session.get(url, headers=headers)
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            if isinstance(data, dict):
                                for key, value in data.items():
                                    if isinstance(value, list):
                                        for item in value:
                                            if isinstance(item, dict) and 'id' in item:
                                                group_id = str(item.get('id'))
                                                group_name = item.get('name') or item.get('title', '')
                                                if group_name and group_id:
                                                    groups[group_name] = group_id
                            elif isinstance(data, list):
                                for item in data:
                                    if isinstance(item, dict) and 'id' in item:
                                        group_id = str(item.get('id'))
                                        group_name = item.get('name') or item.get('title', '')
                                        if group_name and group_id:
                                            groups[group_name] = group_id
                            
                            if groups:
                                print(f"📚 Найдено {len(groups)} групп для {self.crm_type}")
                                break
                        except:
                            pass
                except Exception as e:
                    continue
            
            if groups and self.db:
                for group_name, group_id in groups.items():
                    existing = self.db.get_group(group_id)
                    if not existing:
                        self.db.save_group(group_id, group_name, self.config['site_url'], self.crm_type)
            
            return groups
            
        except Exception as e:
            print(f"Ошибка получения групп: {e}")
            return {}
    
    def get_teacher_groups_sync(self) -> Dict[str, str]:
        """Синхронное получение групп"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_teacher_groups_async())
        finally:
            loop.close()
    
    async def get_lessons_from_api_async(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Асинхронное получение уроков"""
        if not self.is_logged_in:
            if not await self.login_async():
                return []
        
        try:
            if not self.page:
                return []
                
            groups_dict = await self.get_teacher_groups_async()
            
            cookies = await self.page.context.cookies()
            
            csrf_token = None
            try:
                csrf_input = await self.page.query_selector(self.selectors['csrf'])
                if csrf_input:
                    csrf_token = await csrf_input.get_attribute('content')
            except:
                pass
            
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
            session = requests.Session()
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'])
            
            while True:
                params = {'start': start_date, 'end': end_date, 'page': page}
                response = session.get(url, params=params, headers=headers)
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                if total is None:
                    total = data.get('total', 0)
                lessons_data = data.get('collection', [])
                all_lessons.extend(lessons_data)
                
                if len(all_lessons) >= total or not lessons_data:
                    break
                page += 1
            
            # Загружаем календарь
            try:
                await self.page.goto(f"{self.config['site_url']}{self.selectors['schedule_url']}")
                await self.page.wait_for_selector(".fc-view-container", timeout=15000)
                await asyncio.sleep(2)
            except:
                print("⚠️ Не удалось загрузить календарь")
            
            lessons = []
            for lesson_data in all_lessons:
                lesson = self.parse_api_lesson(lesson_data, groups_dict)
                if lesson:
                    lesson_id = lesson.get('id')
                    if lesson_id:
                        popover_data = await self._get_popover_data(lesson_id)
                        if popover_data:
                            for student in lesson.get('students', []):
                                student_id = student.get('id')
                                if student_id and student_id in popover_data:
                                    ps = popover_data[student_id]
                                    student.update(ps)
                    lessons.append(lesson)
            
            print(f"📚 Найдено {len(lessons)} уроков для {self.crm_type}")
            return lessons
            
        except Exception as e:
            print(f"Ошибка получения уроков: {e}")
            return []
    
    def get_lessons_from_api_sync(self, start_date=None, end_date=None) -> List[Dict]:
        """Синхронное получение уроков"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_lessons_from_api_async(start_date, end_date))
        finally:
            loop.close()
    
    def get_lessons_from_api(self, start_date=None, end_date=None) -> List[Dict]:
        """Синхронный вызов (для совместимости)"""
        return self.get_lessons_from_api_sync(start_date, end_date)
    
    async def _get_popover_data(self, lesson_id: str) -> Optional[Dict]:
        """Получение данных поповера"""
        try:
            if not self.page:
                return None
                
            lesson_element = await self.page.query_selector(f"[data-id='{lesson_id}']")
            if not lesson_element:
                return None
            
            await lesson_element.click()
            await asyncio.sleep(0.5)
            
            popover = await self.page.wait_for_selector(".popover", timeout=3000)
            if popover:
                popover_html = await popover.inner_html()
                return self.parse_popover_for_students(popover_html)
            
            return None
        except Exception as e:
            return None
    
    def parse_api_lesson(self, data: Dict, groups_dict: Dict = None) -> Optional[Dict]:
        """Парсинг урока"""
        try:
            status_map = {'1': 'scheduled', '2': 'cancelled', '3': 'completed', '4': 'rescheduled'}
            status = status_map.get(str(data.get('status')), 'scheduled')
            
            type_map = {'1': 'individual', '2': 'group', '3': 'trial', '4': 'tech_support', '5': 'trial'}
            lesson_type = type_map.get(str(data.get('type')), 'unknown')
            
            customers = data.get('customers', {})
            students = []
            customer_id = None
            
            # Извлечение группы
            group_id = None
            group_name = None
            
            if data.get('group_id'):
                group_id = str(data.get('group_id'))
            
            title = data.get('title', '')
            if title:
                match = re.match(r'^([^\(]+)', title)
                if match:
                    potential_name = match.group(1).strip()
                    if re.search(r'[А-ЯA-Z][А-ЯA-Z0-9. ]*\d+', potential_name):
                        group_name = potential_name
            
            if group_name and groups_dict:
                if group_name in groups_dict:
                    group_id = groups_dict[group_name]
                else:
                    for g_name, g_id in groups_dict.items():
                        if group_name in g_name or g_name in group_name:
                            group_id = g_id
                            break
            
            if not group_id and group_name and self.db:
                existing = self.db.get_group_by_name(group_name, self.crm_type)
                if existing:
                    group_id = existing.get('id')
            
            if not group_id and group_name:
                group_id = hashlib.md5(group_name.encode()).hexdigest()[:10]
                if self.db:
                    self.db.save_group(group_id, group_name, self.config['site_url'], self.crm_type)
            
            # Обработка учеников
            if isinstance(customers, dict):
                for cid, name_html in customers.items():
                    clean_name = re.sub(r'<[^>]+>', '', name_html).strip()
                    student = {
                        'id': cid,
                        'name': clean_name,
                        'group_id': group_id,
                        'group_name': group_name,
                        'is_cancelled': '<strike' in name_html,
                        'is_absent': 'text-muted' in name_html,
                        'is_paused': bool(re.search(r'\(пауза', name_html, re.IGNORECASE)),
                    }
                    students.append(student)
                    if not customer_id:
                        customer_id = cid
            
            # Время
            start_time = data.get('start', '')
            duration = data.get('duration', 0)
            time_str = ''
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    time_start = dt.strftime("%H:%M")
                    if duration:
                        dt_end = dt + timedelta(minutes=duration)
                        time_str = f"{time_start} - {dt_end.strftime('%H:%M')}"
                    else:
                        time_str = time_start
                except:
                    time_str = start_time[:5] if len(start_time) >= 5 else ''
            
            return {
                'id': str(data.get('id', '')),
                'time': time_str,
                'client': data.get('title', ''),
                'subject': data.get('subject', ''),
                'topic': data.get('subject', ''),
                'comment': data.get('note', ''),
                'status': status,
                'link': self.config['site_url'] + self.selectors['schedule_url'],
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
        except Exception as e:
            print(f"Ошибка парсинга: {e}")
            return None
    
    def parse_popover_for_students(self, popover_html: str) -> Dict[str, Dict]:
        """Парсинг поповера"""
        try:
            soup = BeautifulSoup(popover_html, 'html.parser')
            students_data = {}
            
            rows = soup.find_all('div', class_='row')
            for row in rows:
                col = row.find('div', class_='col-sm-12')
                if not col:
                    continue
                
                for link in col.find_all('a', href=True):
                    href = link.get('href', '')
                    if 'customer/view' not in href:
                        continue
                    
                    id_match = re.search(r'id=(\d+)', href)
                    if not id_match:
                        continue
                    
                    student_id = id_match.group(1)
                    link_html = str(link)
                    
                    name_span = link.find('span', class_='customer-name')
                    student_name = name_span.get_text(strip=True) if name_span else link.get_text(strip=True)
                    
                    students_data[student_id] = {
                        'id': student_id,
                        'name': student_name,
                        'is_cancelled': '<strike' in link_html,
                        'is_absent': 'text-muted' in link_html,
                        'is_paused': bool(re.search(r'\(пауза', link_html, re.IGNORECASE)),
                        'status_on_lesson': self._extract_status(link_html),
                        'balance': self._extract_balance(link_html),
                    }
            
            return students_data
        except Exception as e:
            return {}
    
    def _extract_status(self, html: str) -> Optional[str]:
        if 'абон' in html.lower() or 'спис' in html.lower():
            return 'списывать'
        elif 'не спис' in html.lower():
            return 'не списывать'
        elif 'пауза' in html.lower():
            return 'пауза'
        return None
    
    def _extract_balance(self, html: str) -> Optional[int]:
        match = re.search(r'\((\d+)\s*(?:ост\.?|уроков?|осталось)\)', html, re.IGNORECASE)
        return int(match.group(1)) if match else None
    
    def save_lesson_relations(self, lesson: Dict, students: List[Dict], group_id: str = None):
        """Сохранение связей (синхронно)"""
        try:
            lesson_id = lesson.get('id')
            crm_type = lesson.get('crm_type')
            site_url = lesson.get('site_url')
            is_completed = lesson.get('status') == 'completed'
            
            if not group_id:
                group_id = lesson.get('group_id')
            
            if group_id and self.db:
                existing = self.db.get_group(group_id)
                if not existing:
                    group_name = lesson.get('group_name', f"Группа #{group_id}")
                    self.db.save_group(group_id, group_name, site_url, crm_type)
                self.db.save_lesson_group(lesson_id, group_id)
            
            for student in students:
                student_id = student.get('id')
                if student_id and self.db:
                    self.db.save_student(
                        student_id=student_id,
                        name=student.get('name', ''),
                        status='active',
                        balance=student.get('balance'),
                        site_url=site_url,
                        crm_type=crm_type
                    )
                    
                    self.db.save_lesson_student(
                        lesson_id=lesson_id,
                        student_id=student_id,
                        status_on_lesson=student.get('status_on_lesson'),
                        is_cancelled=student.get('is_cancelled', False),
                        is_paused=student.get('is_paused', False),
                        is_absent=student.get('is_absent', False),
                        is_rescheduled=student.get('is_rescheduled', False),
                        is_completed=is_completed,
                    )
            
            if self.db:
                self.db.save_lesson(lesson)
        except Exception as e:
            print(f"Ошибка сохранения: {e}")
    
    def save_lesson_relations_sync(self, lesson: Dict, students: List[Dict], group_id: str = None):
        """Синхронное сохранение связей"""
        self.save_lesson_relations(lesson, students, group_id)
    
    # ==================== АСИНХРОННЫЕ МЕТОДЫ ДЛЯ СОВМЕСТИМОСТИ ====================
    
    async def login(self, db) -> bool:
        self.db = db
        return await self.login_async()
    
    async def get_teacher_groups(self, db) -> Dict[str, str]:
        self.db = db
        return await self.get_teacher_groups_async()
    
    async def get_lessons_from_api(self, db, start_date=None, end_date=None) -> List[Dict]:
        self.db = db
        return await self.get_lessons_from_api_async(start_date, end_date)