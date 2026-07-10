# -*- coding: utf-8 -*-
import kivy
kivy.require('2.2.0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.image import Image
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import get_color_from_hex
from kivy.metrics import dp
from datetime import datetime, timedelta
import threading
import base64
import tempfile
import os

from alfacrm_api import AlfaCRMApi
from database import Database
from notification_manager import NotificationManager
from scheduler import Scheduler
from config_manager import ConfigManager

try:
    from logo import LOGO_BASE64
except ImportError:
    LOGO_BASE64 = ""

Window.clearcolor = get_color_from_hex('#0a0a0f')
Window.size = (1200, 800)

class MainApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "AlfaCRM Automation"
        self.db = Database()
        self.config_manager = ConfigManager(db=self.db)
        self.api_instances = []
        self.load_profiles()
        self.notification_manager = NotificationManager(self.db)
        self.scheduler = Scheduler(self.api_instances[0] if self.api_instances else None, self.db, self.notification_manager)
        
    def load_profiles(self):
        profiles = self.config_manager.get_profiles()
        for profile in profiles:
            api = AlfaCRMApi(profile, crm_type=profile.get('crm_type', 'rts'))
            api.db = self.db
            self.api_instances.append(api)
        if not self.api_instances:
            default_profile = {
                'site_url': 'https://rtschool.s20.online',
                'username': '',
                'password': '',
                'crm_type': 'rts'
            }
            api = AlfaCRMApi(default_profile, crm_type='rts')
            api.db = self.db
            self.api_instances.append(api)
        
    def build(self):
        main_layout = BoxLayout(orientation='vertical')
        
        # Шапка
        header = BoxLayout(size_hint_y=None, height=dp(70), padding=[dp(20), dp(10), dp(20), dp(10)], spacing=dp(15))
        with header.canvas.before:
            Color(0.06, 0.06, 0.1, 1)
            header.rect = Rectangle(size=header.size, pos=header.pos)
        header.bind(size=self.update_rect, pos=self.update_rect)
        
        # Логотип
        if LOGO_BASE64:
            try:
                logo_data = base64.b64decode(LOGO_BASE64)
                temp_dir = tempfile.gettempdir()
                logo_path = os.path.join(temp_dir, 'alfacrm_logo.png')
                with open(logo_path, 'wb') as f:
                    f.write(logo_data)
                logo_img = Image(source=logo_path, size_hint_x=None, width=dp(40), height=dp(40))
                header.add_widget(logo_img)
            except Exception as e:
                print(f"Ошибка загрузки логотипа: {e}")
                header.add_widget(Label(text="AlfaCRM", font_size=dp(16), bold=True,
                                        color=get_color_from_hex('#888899'), size_hint_x=None, width=dp(100)))
        else:
            header.add_widget(Label(text="AlfaCRM", font_size=dp(16), bold=True,
                                    color=get_color_from_hex('#888899'), size_hint_x=None, width=dp(100)))
        
        title = Label(text="Automation", color=get_color_from_hex('#ffffff'),
                      font_size=dp(22), bold=True, size_hint_x=0.6)
        header.add_widget(title)
        
        # Статус
        status_box = BoxLayout(size_hint_x=0.1, spacing=dp(2))
        self.status_indicator = Label(text="•", color=get_color_from_hex('#ff4444'),
                                      font_size=dp(72), size_hint_x=None, width=dp(40))
        status_box.add_widget(self.status_indicator)
        self.status_text = Label(text="Нет подключения", color=get_color_from_hex('#888899'), font_size=dp(14))
        status_box.add_widget(self.status_text)
        header.add_widget(status_box)
        
        self.lesson_count = Label(text="0 уроков", color=get_color_from_hex('#666677'),
                                  font_size=dp(14), size_hint_x=0.2, halign='right')
        header.add_widget(self.lesson_count)
        main_layout.add_widget(header)
        
        # Вкладки
        tabs = TabbedPanel(do_default_tab=False, tab_width=dp(160), tab_height=dp(45))
        with tabs.canvas.before:
            Color(0.05, 0.05, 0.08, 1)
            tabs.rect = Rectangle(size=tabs.size, pos=tabs.pos)
        tabs.bind(size=self.update_rect, pos=self.update_rect)
        
        # Календарь
        calendar_tab = TabbedPanelItem(text="Календарь")
        self.calendar_widget = CalendarWidget(self.db, self.api_instances)
        calendar_tab.add_widget(self.calendar_widget)
        tabs.add_widget(calendar_tab)
        
        # Уведомления
        notif_tab = TabbedPanelItem(text="Уведомления")
        notif_tab.add_widget(NotificationsTab(self.db))
        tabs.add_widget(notif_tab)
        
        # Настройки
        settings_tab = TabbedPanelItem(text="Настройки")
        settings_tab.add_widget(SettingsTab(self))
        tabs.add_widget(settings_tab)
        
        main_layout.add_widget(tabs)
        
        # Нижняя строка
        status_bar = BoxLayout(size_hint_y=None, height=dp(35), padding=[dp(20), dp(5), dp(20), dp(5)])
        with status_bar.canvas.before:
            Color(0.05, 0.05, 0.08, 1)
            status_bar.rect = Rectangle(size=status_bar.size, pos=status_bar.pos)
        status_bar.bind(size=self.update_rect, pos=self.update_rect)
        info_label = Label(text="Двойной клик по уроку – подробности | Масштаб +/-",
                           color=get_color_from_hex('#444455'), font_size=dp(11), halign='left')
        status_bar.add_widget(info_label)
        main_layout.add_widget(status_bar)
        
        if self.config_manager.get('auto_start', False):
            self.scheduler.start()
        Clock.schedule_once(self.check_connection, 2)
        return main_layout
        
    def check_connection(self, dt):
        if any(api.config.get('username') for api in self.api_instances):
            threading.Thread(target=self.test_login, daemon=True).start()
            
    def test_login(self):
        """Асинхронный вход с запуском отдельных потоков для каждого профиля"""
        threads = []
        results = {}
        def login_api(api):
            try:
                success = api.login()
                results[api.crm_type] = success
            except Exception as e:
                print(f"Ошибка входа для {api.crm_type}: {e}")
                results[api.crm_type] = False
        for api in self.api_instances:
            # Пропускаем профили без логина
            if not api.config.get('username'):
                results[api.crm_type] = False
                continue
            t = threading.Thread(target=login_api, args=(api,))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        # Обработка результатов
        if all(results.values()):
            Clock.schedule_once(lambda dt: self.update_status('Подключено', '#44ff44'))
            threading.Thread(target=self.async_load_lessons, daemon=True).start()
        elif any(results.values()):
            Clock.schedule_once(lambda dt: self.update_status('Частичное подключение', '#ffaa44'))
        else:
            Clock.schedule_once(lambda dt: self.update_status('Нет подключения', '#ff4444'))
        # Выводим детали
        for crm, status in results.items():
            print(f"{crm}: {'Успешно' if status else 'Ошибка'}")

    def async_load_lessons(self):
        Clock.schedule_once(lambda dt: self.update_status('Загрузка уроков...', '#44aaff'))
        Clock.schedule_once(lambda dt: self.calendar_widget.load_week_lessons(), 0.5)
        Clock.schedule_once(lambda dt: self.calendar_widget.rebuild_table(), 1)
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_end = week_start + timedelta(days=6)
        lessons = self.db.get_lessons_for_period(week_start.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d"))
        Clock.schedule_once(lambda dt: self.update_lesson_count(len(lessons)))
        Clock.schedule_once(lambda dt: self.update_status('Подключено', '#44ff44'))
            
    def update_status(self, text, color):
        self.status_text.text = text
        self.status_indicator.color = get_color_from_hex(color)
    
    def update_lesson_count(self, count):
        self.lesson_count.text = f"{count} уроков"
        
    def update_rect(self, instance, value):
        if hasattr(instance, 'rect'):
            instance.rect.pos = instance.pos
            instance.rect.size = instance.size
        
    def on_stop(self):
        if hasattr(self, 'scheduler'):
            self.scheduler.stop()
        for api in self.api_instances:
            api.close()

# ============================== КАЛЕНДАРЬ ==============================
class CalendarWidget(BoxLayout):
    def __init__(self, db, api_instances, **kwargs):
        super().__init__(**kwargs)
        self.db = db
        self.api_instances = api_instances
        self.orientation = 'vertical'
        self.current_date = datetime.now()
        self.hours = list(range(8, 22))
        self.zoom_level = 1.0
        self.data_loaded = False
        self.current_week_start_str = None
        self.current_week_end_str = None
        self.lessons_by_day_cache = {}
        self.scroll = None
        self.calendar_grid = None
        Clock.schedule_once(lambda dt: self.build_calendar(), 0.1)
        Window.bind(on_resize=self.on_window_resize)
        
    def on_window_resize(self, window, width, height):
        self.rebuild_table()
        
    def build_calendar(self):
        self.clear_widgets()
        
        # Навигация
        nav = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(10), padding=[dp(15), dp(5), dp(15), dp(5)])
        with nav.canvas.before:
            Color(0.08, 0.08, 0.12, 1)
            nav.rect = Rectangle(size=nav.size, pos=nav.pos)
        nav.bind(size=self.update_rect, pos=self.update_rect)
        
        prev_btn = Button(text="<", size_hint_x=None, width=dp(50),
                          background_color=(0.15, 0.15, 0.2, 1), color=(1,1,1,1),
                          font_size=dp(20), bold=True)
        prev_btn.bind(on_press=self.prev_week)
        nav.add_widget(prev_btn)
        
        week_start = self.current_date - timedelta(days=self.current_date.weekday())
        week_end = week_start + timedelta(days=6)
        week_label = Label(text=f"{week_start.strftime('%d.%m.%Y')} — {week_end.strftime('%d.%m.%Y')}",
                           color=get_color_from_hex('#ffffff'), font_size=dp(18), bold=True)
        nav.add_widget(week_label)
        
        today_btn = Button(text="Сегодня", size_hint_x=None, width=dp(100),
                           background_color=(0.15, 0.4, 0.15, 1), color=(1,1,1,1),
                           font_size=dp(13), bold=True)
        today_btn.bind(on_press=self.go_today)
        nav.add_widget(today_btn)
        
        zoom_box = BoxLayout(size_hint_x=None, width=dp(120), spacing=dp(5))
        zoom_out = Button(text="-", size_hint_x=None, width=dp(35),
                          background_color=(0.15, 0.15, 0.2, 1), color=(1,1,1,1),
                          font_size=dp(20), bold=True)
        zoom_out.bind(on_press=lambda x: self.zoom(-0.1))
        zoom_box.add_widget(zoom_out)
        self.zoom_label = Label(text=f"{int(self.zoom_level*100)}%",
                                color=get_color_from_hex('#888899'),
                                font_size=dp(12), size_hint_x=None, width=dp(40))
        zoom_box.add_widget(self.zoom_label)
        zoom_in = Button(text="+", size_hint_x=None, width=dp(35),
                         background_color=(0.15, 0.15, 0.2, 1), color=(1,1,1,1),
                         font_size=dp(20), bold=True)
        zoom_in.bind(on_press=lambda x: self.zoom(0.1))
        zoom_box.add_widget(zoom_in)
        nav.add_widget(zoom_box)
        
        next_btn = Button(text=">", size_hint_x=None, width=dp(50),
                          background_color=(0.15, 0.15, 0.2, 1), color=(1,1,1,1),
                          font_size=dp(20), bold=True)
        next_btn.bind(on_press=self.next_week)
        nav.add_widget(next_btn)
        self.add_widget(nav)
        
        # Индикатор загрузки
        self.loading_label = Label(text="Загрузка уроков...", color=get_color_from_hex('#888899'),
                                    font_size=dp(20), size_hint=(1, 1))
        self.add_widget(self.loading_label)
        
        # Запускаем загрузку в фоне
        threading.Thread(target=self.async_load_and_build, daemon=True).start()
        
    def async_load_and_build(self):
        self.load_week_lessons()
        Clock.schedule_once(lambda dt: self.finish_build(), 0)
        
    def finish_build(self):
        # Убираем индикатор
        self.remove_widget(self.loading_label)
        # Создаём ScrollView
        self.scroll = ScrollView(do_scroll_x=True, do_scroll_y=True,
                                bar_width=dp(8), bar_color=(0.3,0.3,0.5,0.8))
        # Создаём GridLayout
        self.calendar_grid = GridLayout(cols=8, spacing=1, size_hint=(1, 1))
        self.build_table()
        self.scroll.add_widget(self.calendar_grid)
        self.add_widget(self.scroll)
        
    def load_week_lessons(self):
        week_start = self.current_date - timedelta(days=self.current_date.weekday())
        week_end = week_start + timedelta(days=6)
        start_str = week_start.strftime("%Y-%m-%d")
        end_str = week_end.strftime("%Y-%m-%d")
        
        if (self.current_week_start_str == start_str and 
            self.current_week_end_str == end_str and 
            self.data_loaded):
            return
        
        self.current_week_start_str = start_str
        self.current_week_end_str = end_str
        
        all_lessons = []
        for api in self.api_instances:
            try:
                lessons = api.get_lessons_from_api(start_str, end_str)
                if lessons:
                    all_lessons.extend(lessons)
            except Exception as e:
                print(f"Ошибка загрузки из {api.crm_type}: {e}")
        
        if all_lessons:
            self.db.save_lessons(all_lessons)
        
        self.week_lessons = self.db.get_lessons_for_period(start_str, end_str)
        self.lessons_by_day_cache = {}
        for lesson in self.week_lessons:
            day = lesson.get('date', '')
            if day:
                self.lessons_by_day_cache.setdefault(day, []).append(lesson)
        self.data_loaded = True
        
    def rebuild_table(self):
        if self.calendar_grid:
            self.calendar_grid.clear_widgets()
            self.build_table()
        
    def build_table(self):
        if not self.calendar_grid:
            return
        self.calendar_grid.clear_widgets()
        win_width, win_height = Window.size
        available_height = win_height - dp(130) - dp(60) - dp(35)
        available_width = win_width - dp(20)
        rows = len(self.hours) + 1
        cols = 8
        row_h = max(30, (available_height / rows) * self.zoom_level)
        col_w = max(80, (available_width / cols) * self.zoom_level)
        row_h = max(30, row_h)
        col_w = max(80, col_w)
        
        self.add_header_row(row_h, col_w)
        self.add_time_rows(row_h, col_w)
        
    def add_header_row(self, row_h, col_w):
        corner = Label(text="Час", color=get_color_from_hex('#888899'),
                       font_size=dp(12), bold=True,
                       size_hint=(None, None), size=(col_w, row_h))
        with corner.canvas.before:
            Color(0.08, 0.08, 0.12, 1)
            corner.rect = Rectangle(size=corner.size, pos=corner.pos)
        corner.bind(size=self.update_rect, pos=self.update_rect)
        self.calendar_grid.add_widget(corner)
        
        week_start = self.current_date - timedelta(days=self.current_date.weekday())
        days_short = ['ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС']
        for i in range(7):
            day_date = week_start + timedelta(days=i)
            is_today = day_date.date() == datetime.now().date()
            is_weekend = i >= 5
            
            container = BoxLayout(orientation='vertical',
                                  size_hint=(None, None), size=(col_w, row_h),
                                  padding=[dp(2), dp(1), dp(2), dp(1)])
            bg = (0.15,0.25,0.4,1) if is_today else (0.08,0.08,0.12,1)
            if is_weekend and not is_today:
                bg = (0.06,0.06,0.12,1)
            with container.canvas.before:
                Color(*bg)
                container.rect = Rectangle(size=container.size, pos=container.pos)
            container.bind(size=self.update_rect, pos=self.update_rect)
            
            day_lbl = Label(text=days_short[i],
                            color=get_color_from_hex('#ffffff') if is_today else get_color_from_hex('#888899'),
                            font_size=dp(10), bold=is_today,
                            size_hint_y=None, height=row_h*0.5)
            container.add_widget(day_lbl)
            
            num_lbl = Label(text=day_date.strftime("%d"),
                            color=get_color_from_hex('#66ccff') if is_today else get_color_from_hex('#666677'),
                            font_size=dp(14), bold=True,
                            size_hint_y=None, height=row_h*0.5)
            container.add_widget(num_lbl)
            self.calendar_grid.add_widget(container)
            
    def add_time_rows(self, row_h, col_w):
        week_start = self.current_date - timedelta(days=self.current_date.weekday())
        for hour in self.hours:
            time_str = f"{hour:02d}:00"
            curr_h = row_h
            
            time_lbl = Label(text=time_str, color=get_color_from_hex('#555566'),
                             font_size=dp(10),
                             size_hint=(None, None), size=(col_w, curr_h))
            with time_lbl.canvas.before:
                Color(0.05, 0.05, 0.08, 1)
                time_lbl.rect = Rectangle(size=time_lbl.size, pos=time_lbl.pos)
            time_lbl.bind(size=self.update_rect, pos=self.update_rect)
            self.calendar_grid.add_widget(time_lbl)
            
            for i in range(7):
                day_date = week_start + timedelta(days=i)
                date_str = day_date.strftime("%Y-%m-%d")
                is_weekend = i >= 5
                
                cell = BoxLayout(orientation='vertical',
                                 size_hint=(None, None), size=(col_w, curr_h),
                                 padding=[dp(2), dp(1), dp(2), dp(1)])
                bg = (0.04,0.04,0.08,1) if is_weekend else (0.07,0.07,0.1,1)
                with cell.canvas.before:
                    Color(*bg)
                    cell.rect = Rectangle(size=cell.size, pos=cell.pos)
                cell.bind(size=self.update_rect, pos=self.update_rect)
                
                lessons_in_hour = []
                if date_str in self.lessons_by_day_cache:
                    for l in self.lessons_by_day_cache[date_str]:
                        l_time = l.get('time', '')
                        if l_time and l_time.startswith(f"{hour:02d}:"):
                            lessons_in_hour.append(l)
                
                if lessons_in_hour:
                    # Создаём вертикальный контейнер для нескольких уроков
                    if len(lessons_in_hour) == 1:
                        widget = self.create_lesson_widget(lessons_in_hour[0], curr_h, col_w)
                        cell.add_widget(widget)
                    else:
                        multi_box = BoxLayout(orientation='vertical', size_hint=(1, 1), spacing=dp(1))
                        for lesson in lessons_in_hour:
                            single_widget = self.create_lesson_widget(lesson, curr_h/len(lessons_in_hour), col_w)
                            single_widget.size_hint_y = None
                            single_widget.height = curr_h/len(lessons_in_hour) - dp(1)
                            multi_box.add_widget(single_widget)
                        cell.add_widget(multi_box)
                
                self.calendar_grid.add_widget(cell)
                    
    def create_lesson_widget(self, lesson, height, width):
        box = BoxLayout(orientation='vertical',
                        size_hint=(None, None),
                        size=(width-dp(4), height-dp(2)),
                        padding=[dp(2), dp(2), dp(2), dp(2)])
        
        status = lesson.get('status', 'scheduled')
        ltype = lesson.get('type', 'unknown')
        is_occupied = lesson.get('is_occupied', False)
        
        # Определяем цвет фона и текста
        if status == 'cancelled':
            bg = (0.2, 0.2, 0.2, 0.95)       # угольный
            border = (0.4, 0.4, 0.4, 1)
            text_color = (0.8, 0.8, 0.8, 1)
        elif status == 'completed':
            bg = (0.1, 0.4, 0.1, 0.9)        # зелёный
            border = (0.3, 0.6, 0.3, 1)
            text_color = (1, 1, 1, 1)
        elif ltype == 'trial':
            bg = (0.75, 0.75, 0.75, 0.9)     # светло-серый
            border = (0.7, 0.7, 0.7, 1)
            text_color = (0.2, 0.2, 0.2, 1)
        elif ltype in ['individual', 'group', 'tech_support']:
            bg = (0.29, 0.56, 0.85, 0.9)     # голубой (4A90D9)
            border = (0.4, 0.7, 0.9, 1)
            text_color = (1, 1, 1, 1)
        else:
            bg = (0.13, 0.59, 0.95, 0.9)     # стандартный синий (2196F3)
            border = (0.2, 0.7, 1, 1)
            text_color = (1, 1, 1, 1)
        
        # Нижняя граница по CRM
        crm_type = lesson.get('crm_type', 'rts')
        if crm_type == 'wellkid':
            bottom_color = (1.0, 0.6, 0.0, 1)
        else:
            bottom_color = (0.0, 0.2, 0.6, 1)
        
        with box.canvas.before:
            Color(*bg)
            box.rect = RoundedRectangle(size=box.size, pos=box.pos, radius=[(dp(4), dp(4))])
            Color(*bottom_color)
            box.bottom_border = Rectangle(size=(box.width, dp(4)), pos=(box.x, box.y))
        box.bind(size=self.update_rect, pos=self.update_rect)
        
        # Время
        time_display = lesson.get('time', '')
        time_lbl = Label(text=time_display, color=(1,1,1,1),
                        font_size=dp(9), bold=True,
                        size_hint_y=None, height=height*0.3,
                        text_size=(width-dp(10), None), halign='left')
        box.add_widget(time_lbl)
        
        # Имя клиента или список учеников (для группы)
        lesson_type = lesson.get('type', '')
        if lesson_type == 'group':
            students = lesson.get('students', [])
            if students:
                names = [s.get('name', '') for s in students[:2]]
                if len(students) > 2:
                    names.append(f"+{len(students)-2}")
                client_text = ", ".join(names)
            else:
                client_text = lesson.get('client', 'Группа')
        else:
            client_text = lesson.get('client', '')
        
        client_lbl = Label(text=client_text, color=text_color, font_size=dp(9), bold=True,
                        size_hint_y=None, height=height*0.4,
                        text_size=(width-dp(10), None), halign='left', shorten=True)
        box.add_widget(client_lbl)
        
        # Статус-символ
        status_symbols = {'scheduled': 'P', 'completed': 'C', 'cancelled': 'X'}
        sym = status_symbols.get(status, '')
        if sym:
            status_lbl = Label(text=sym, color=text_color, font_size=dp(8),
                            size_hint_y=None, height=height*0.3,
                            halign='right')
            box.add_widget(status_lbl)
        
        box.lesson = lesson
        box.bind(on_touch_down=self._on_lesson_click)
        return box
        
    def _on_lesson_click(self, instance, touch):
        if instance.collide_point(*touch.pos):
            if hasattr(instance, 'lesson'):
                self.show_lesson_details(instance.lesson)
            return True
        return False
        
    def show_lesson_details(self, lesson):
        content = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        title = Label(text=f"Урок {lesson.get('time', '')}",
                    color=get_color_from_hex('#ffffff'), font_size=dp(20),
                    bold=True, size_hint_y=None, height=dp(45))
        content.add_widget(title)
        
        sep = BoxLayout(size_hint_y=None, height=dp(2))
        with sep.canvas.before:
            Color(0.2,0.2,0.3,1)
            sep.rect = Rectangle(size=sep.size, pos=sep.pos)
        sep.bind(size=self.update_rect, pos=self.update_rect)
        content.add_widget(sep)
        
        status_names = {'scheduled':'Запланирован','cancelled':'Отменён','completed':'Проведён'}
        type_names = {'individual':'Индивидуальный','group':'Групповой',
                    'trial':'Пробный','tech_support':'Техподдержка'}
        
        students = lesson.get('students', [])
        if students:
            info_text = f"""
    Статус: {status_names.get(lesson.get('status', ''), 'Неизвестен')}
    Тип: {type_names.get(lesson.get('type', ''), 'Неизвестен')}
    Дата: {lesson.get('date', 'Не указана')}
    Время: {lesson.get('time', 'Не указано')}
    Комментарий: {lesson.get('comment', 'Нет')}
    Преподаватель: {lesson.get('teacher', 'Не указан')}
    Кабинет: {lesson.get('room', 'Не указан')}
    CRM: {lesson.get('crm_type', 'неизвестно')}

    Ученики:
    """
            for s in students:
                status_icon = ""
                if s.get('is_cancelled'):
                    status_icon = "✕ "
                elif s.get('is_paused'):
                    status_icon = "⏸ "
                info_text += f"  {status_icon}{s.get('name')}"
                if s.get('pause_info'):
                    info_text += f" (пауза {s.get('pause_info')})"
                info_text += "\n"
        else:
            info_text = f"""
    Клиент(ы): {lesson.get('client', 'Не указан')}
    Статус: {status_names.get(lesson.get('status', ''), 'Неизвестен')}
    Тип: {type_names.get(lesson.get('type', ''), 'Неизвестен')}
    Дата: {lesson.get('date', 'Не указана')}
    Время: {lesson.get('time', 'Не указано')}
    Комментарий: {lesson.get('comment', 'Нет')}
    Преподаватель: {lesson.get('teacher', 'Не указан')}
    Кабинет: {lesson.get('room', 'Не указан')}
    CRM: {lesson.get('crm_type', 'неизвестно')}
    """
        
        info_lbl = Label(text=info_text, color=get_color_from_hex('#ccccdd'),
                        font_size=dp(14), size_hint_y=None, height=dp(240),
                        halign='left', valign='top', text_size=(dp(400), None))
        content.add_widget(info_lbl)
        
        # Кнопки
        btn_box = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        customer_id = lesson.get('customer_id')
        site_url = lesson.get('site_url', '')
        if customer_id and site_url:
            lesson_url = f"{site_url}/teacher/1/customer/view?id={customer_id}"
        else:
            lesson_id = lesson.get('id')
            if lesson_id and site_url:
                lesson_url = f"{site_url}/teacher/1/lesson/view?id={lesson_id}"
            else:
                lesson_url = lesson.get('link', '')
        if lesson_url:
            link_btn = Button(text="Открыть в браузере",
                            background_color=(0.15,0.4,0.8,1), color=(1,1,1,1),
                            font_size=dp(13), bold=True)
            link_btn.bind(on_press=lambda x: self.open_link(lesson_url))
            btn_box.add_widget(link_btn)
        close_btn = Button(text="Закрыть",
                        background_color=(0.2,0.2,0.3,1), color=(1,1,1,1),
                        font_size=dp(13), bold=True)
        close_btn.bind(on_press=self.dismiss_popup)
        btn_box.add_widget(close_btn)
        content.add_widget(btn_box)
        
        self.popup = Popup(title='', content=content, size_hint=(0.75, 0.65),
                        background_color=(0.05,0.05,0.08,1))
        close_btn.bind(on_press=self.popup.dismiss)
        self.popup.open()
        
    def dismiss_popup(self, instance):
        if hasattr(self, 'popup'):
            self.popup.dismiss()
        
    def open_link(self, url):
        import webbrowser
        webbrowser.open(url)
        
    def zoom(self, delta):
        new_zoom = self.zoom_level + delta
        if 0.5 <= new_zoom <= 1.5:
            self.zoom_level = new_zoom
            self.zoom_label.text = f"{int(self.zoom_level*100)}%"
            self.rebuild_table()
            
    def update_rect(self, instance, value):
        for attr in ['rect', 'border', 'bottom_border']:
            if hasattr(instance, attr):
                obj = getattr(instance, attr)
                if attr == 'bottom_border':
                    obj.size = (instance.width, dp(4))
                    obj.pos = (instance.x, instance.y)
                else:
                    obj.pos = instance.pos
                    obj.size = instance.size
        if hasattr(instance, 'children'):
            for child in instance.children:
                self.update_rect(child, value)
                
    def prev_week(self, instance):
        self.current_date -= timedelta(days=7)
        self.data_loaded = False
        self.build_calendar()
        
    def next_week(self, instance):
        self.current_date += timedelta(days=7)
        self.data_loaded = False
        self.build_calendar()
        
    def go_today(self, instance):
        self.current_date = datetime.now()
        self.data_loaded = False
        self.build_calendar()


# ============================== НАСТРОЙКИ ==============================
class SettingsTab(BoxLayout):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.padding = dp(20)
        self.spacing = dp(15)
        self.build_settings()
        
    def build_settings(self):
        self.clear_widgets()
        
        title = Label(text="Настройки", color=get_color_from_hex('#ffffff'),
                      font_size=dp(24), bold=True, size_hint_y=None, height=dp(50))
        self.add_widget(title)
        
        scroll = ScrollView(bar_width=dp(6))
        content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(15))
        content.bind(minimum_height=content.setter('height'))
        
        # Группа: Подключение (профили)
        group1 = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10))
        group1_label = Label(text="Профили CRM", color=get_color_from_hex('#66ccff'),
                             font_size=dp(16), bold=True, size_hint_y=None, height=dp(30))
        group1.add_widget(group1_label)
        
        profiles = self.app.config_manager.get_profiles()
        self.profile_widgets = []
        for idx, profile in enumerate(profiles):
            prof_box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(200), spacing=dp(5))
            prof_box.border_color = get_color_from_hex('#333344')
            with prof_box.canvas.before:
                Color(0.1, 0.1, 0.15, 1)
                prof_box.rect = RoundedRectangle(size=prof_box.size, pos=prof_box.pos, radius=[(dp(6), dp(6))])
            prof_box.bind(size=self.update_rect, pos=self.update_rect)
            
            # Заголовок профиля
            header_box = BoxLayout(size_hint_y=None, height=dp(30))
            crm_label = Label(text=profile.get('crm_type', 'rts').upper(), color=get_color_from_hex('#88ccff'),
                              font_size=dp(13), bold=True, size_hint_x=0.3)
            header_box.add_widget(crm_label)
            header_box.add_widget(Label(text="", size_hint_x=0.7))
            prof_box.add_widget(header_box)
            
            # Поля
            fields = [
                ('URL:', 'site_url'),
                ('Логин:', 'username'),
                ('Пароль:', 'password')
            ]
            entries = {}
            for label_text, key in fields:
                container = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(5))
                label = Label(text=label_text, color=get_color_from_hex('#888899'),
                              font_size=dp(11), size_hint_x=0.25, halign='right')
                container.add_widget(label)
                is_pwd = 'пароль' in label_text.lower() or 'password' in label_text.lower()
                entry = TextInput(text=str(profile.get(key, '')),
                                  size_hint_x=0.75, height=dp(30),
                                  background_color=(0.12,0.12,0.18,1),
                                  foreground_color=(1,1,1,1),
                                  cursor_color=(0.3,0.6,1,1),
                                  password=is_pwd,
                                  font_size=dp(12), padding=[dp(8), dp(3)])
                container.add_widget(entry)
                entries[key] = entry
                prof_box.add_widget(container)
            
            crm_type_entry = TextInput(text=profile.get('crm_type', 'rts'), size_hint_y=None, height=0, opacity=0)
            prof_box.add_widget(crm_type_entry)
            entries['crm_type'] = crm_type_entry
            
            prof_box.entries = entries
            self.profile_widgets.append(prof_box)
            content.add_widget(prof_box)
        
        # Кнопка добавления профиля
        add_btn = Button(text="+ Добавить профиль", size_hint_y=None, height=dp(40),
                         background_color=(0.15,0.3,0.5,1), color=(1,1,1,1),
                         font_size=dp(13), bold=True)
        add_btn.bind(on_press=self.add_profile)
        content.add_widget(add_btn)
        
        sep = BoxLayout(size_hint_y=None, height=dp(2))
        with sep.canvas.before:
            Color(0.2,0.2,0.3,1)
            sep.rect = Rectangle(size=sep.size, pos=sep.pos)
        sep.bind(size=self.update_rect, pos=self.update_rect)
        content.add_widget(sep)
        
        # Группа: Расписание
        group2 = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(120), spacing=dp(10))
        group2_label = Label(text="Расписание и уведомления", color=get_color_from_hex('#66ccff'),
                             font_size=dp(16), bold=True, size_hint_y=None, height=dp(30))
        group2.add_widget(group2_label)
        
        container = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        label = Label(text="Интервал проверки (часы):", color=get_color_from_hex('#888899'),
                      font_size=dp(13), size_hint_x=0.4, halign='right')
        container.add_widget(label)
        entry = TextInput(text=str(self.app.config_manager.get('check_interval_hours', 1)),
                          size_hint_x=0.6, height=dp(40),
                          background_color=(0.12,0.12,0.18,1),
                          foreground_color=(1,1,1,1),
                          cursor_color=(0.3,0.6,1,1),
                          font_size=dp(13), padding=[dp(10), dp(5)])
        container.add_widget(entry)
        self.entries = {'check_interval_hours': entry}
        group2.add_widget(container)
        
        auto_box = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(10))
        auto_box.add_widget(Label(text="Автозапуск при старте:", color=get_color_from_hex('#888899'),
                                  font_size=dp(13), size_hint_x=0.4, halign='right'))
        self.auto_btn = Button(text="Вкл" if self.app.config_manager.get('auto_start', False) else "Выкл",
                               size_hint_x=0.6, height=dp(40),
                               background_color=(0.15,0.4,0.15,1) if self.app.config_manager.get('auto_start', False) else (0.3,0.3,0.3,1),
                               color=(1,1,1,1), font_size=dp(13), bold=True)
        self.auto_btn.bind(on_press=self.toggle_auto_start)
        auto_box.add_widget(self.auto_btn)
        group2.add_widget(auto_box)
        content.add_widget(group2)
        
        sep2 = BoxLayout(size_hint_y=None, height=dp(2))
        with sep2.canvas.before:
            Color(0.2,0.2,0.3,1)
            sep2.rect = Rectangle(size=sep2.size, pos=sep2.pos)
        sep2.bind(size=self.update_rect, pos=self.update_rect)
        content.add_widget(sep2)
        
        btn_box = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10), padding=[dp(0), dp(10), dp(0), dp(0)])
        save_btn = Button(text="Сохранить",
                          background_color=(0.15,0.4,0.8,1), color=(1,1,1,1),
                          font_size=dp(14), bold=True)
        save_btn.bind(on_press=self.save_settings)
        btn_box.add_widget(save_btn)
        
        test_btn = Button(text="Проверить подключение",
                          background_color=(0.2,0.2,0.3,1), color=(1,1,1,1),
                          font_size=dp(14), bold=True)
        test_btn.bind(on_press=self.test_connection)
        btn_box.add_widget(test_btn)
        content.add_widget(btn_box)
        
        self.status_label = Label(text="", color=get_color_from_hex('#66cc66'),
                                  size_hint_y=None, height=dp(30), font_size=dp(13))
        content.add_widget(self.status_label)
        
        scroll.add_widget(content)
        self.add_widget(scroll)
        
    def add_profile(self, instance):
        prof_box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(200), spacing=dp(5))
        prof_box.border_color = get_color_from_hex('#333344')
        with prof_box.canvas.before:
            Color(0.1, 0.1, 0.15, 1)
            prof_box.rect = RoundedRectangle(size=prof_box.size, pos=prof_box.pos, radius=[(dp(6), dp(6))])
        prof_box.bind(size=self.update_rect, pos=self.update_rect)
        
        header_box = BoxLayout(size_hint_y=None, height=dp(30))
        crm_label = Label(text="НОВЫЙ", color=get_color_from_hex('#88ccff'),
                          font_size=dp(13), bold=True, size_hint_x=0.3)
        header_box.add_widget(crm_label)
        header_box.add_widget(Label(text="", size_hint_x=0.7))
        prof_box.add_widget(header_box)
        
        entries = {}
        for label_text, key in [('URL:', 'site_url'), ('Логин:', 'username'), ('Пароль:', 'password')]:
            container = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(5))
            label = Label(text=label_text, color=get_color_from_hex('#888899'),
                          font_size=dp(11), size_hint_x=0.25, halign='right')
            container.add_widget(label)
            is_pwd = 'пароль' in label_text.lower() or 'password' in label_text.lower()
            entry = TextInput(text='', size_hint_x=0.75, height=dp(30),
                              background_color=(0.12,0.12,0.18,1),
                              foreground_color=(1,1,1,1),
                              cursor_color=(0.3,0.6,1,1),
                              password=is_pwd,
                              font_size=dp(12), padding=[dp(8), dp(3)])
            container.add_widget(entry)
            entries[key] = entry
            prof_box.add_widget(container)
        crm_type_entry = TextInput(text='rts', size_hint_y=None, height=0, opacity=0)
        prof_box.add_widget(crm_type_entry)
        entries['crm_type'] = crm_type_entry
        
        prof_box.entries = entries
        parent = instance.parent
        parent.add_widget(prof_box, index=parent.children.index(instance))
        self.profile_widgets.append(prof_box)
        
    def toggle_auto_start(self, instance):
        current = self.app.config_manager.get('auto_start', False)
        new_val = not current
        self.app.config_manager.set('auto_start', new_val)
        instance.text = "Вкл" if new_val else "Выкл"
        instance.background_color = (0.15,0.4,0.15,1) if new_val else (0.3,0.3,0.3,1)
        
    def save_settings(self, instance):
        profiles = []
        for prof_box in self.profile_widgets:
            entries = prof_box.entries
            profile = {
                'site_url': entries['site_url'].text,
                'username': entries['username'].text,
                'password': entries['password'].text,
                'crm_type': entries['crm_type'].text if entries['crm_type'].text else 'rts'
            }
            if profile['site_url'] and profile['username']:
                profiles.append(profile)
        self.app.config_manager.save_profiles(profiles)
        
        try:
            interval = int(self.entries['check_interval_hours'].text)
            if interval < 1: interval = 1
            self.app.config_manager.set('check_interval_hours', interval)
            self.app.scheduler.set_check_interval(interval)
        except: pass
        
        self.app.api_instances = []
        self.app.load_profiles()
        self.app.calendar_widget.api_instances = self.app.api_instances
        self.app.calendar_widget.data_loaded = False
        self.app.calendar_widget.build_calendar()
        
        self.status_label.text = "Настройки сохранены"
        self.status_label.color = get_color_from_hex('#66cc66')
        
    def test_connection(self, instance):
        self.status_label.text = "Проверка подключения..."
        self.status_label.color = get_color_from_hex('#cccc00')
        def test():
            try:
                for api in self.app.api_instances:
                    if not api.login():
                        self.update_status("Ошибка подключения к одному из профилей", get_color_from_hex('#ff6666'))
                        return
                self.update_status("Подключение успешно", get_color_from_hex('#66cc66'))
            except Exception as e:
                self.update_status(f"Ошибка: {str(e)[:50]}", get_color_from_hex('#ff6666'))
        threading.Thread(target=test).start()
        
    def update_status(self, text, color):
        Clock.schedule_once(lambda dt: self._update_status(text, color))
        
    def _update_status(self, text, color):
        self.status_label.text = text
        self.status_label.color = color
        
    def update_rect(self, instance, value):
        if hasattr(instance, 'rect'):
            instance.rect.pos = instance.pos
            instance.rect.size = instance.size


# ============================== УВЕДОМЛЕНИЯ ==============================
class NotificationsTab(BoxLayout):
    def __init__(self, db, **kwargs):
        super().__init__(**kwargs)
        self.db = db
        self.orientation = 'vertical'
        self.padding = dp(20)
        self.spacing = dp(10)
        self.build_notifications()
        
    def build_notifications(self):
        self.clear_widgets()
        title = Label(text="Уведомления", color=get_color_from_hex('#ffffff'),
                      font_size=dp(24), bold=True, size_hint_y=None, height=dp(50))
        self.add_widget(title)
        
        scroll = ScrollView(bar_width=dp(6))
        layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(5))
        layout.bind(minimum_height=layout.setter('height'))
        
        notifications = self.db.get_notifications(100)
        if not notifications:
            no = Label(text="Нет уведомлений", color=get_color_from_hex('#555566'),
                       font_size=dp(16), size_hint_y=None, height=dp(200))
            layout.add_widget(no)
        else:
            for notif in notifications:
                box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(80),
                                padding=dp(10), spacing=dp(3))
                with box.canvas.before:
                    Color(0.08,0.08,0.12,1)
                    box.rect = RoundedRectangle(size=box.size, pos=box.pos, radius=[(dp(6), dp(6))])
                box.bind(size=self.update_rect, pos=self.update_rect)
                msg = Label(text=notif.get('message', ''), color=get_color_from_hex('#ccccdd'),
                            font_size=dp(13), size_hint_y=None, height=dp(40),
                            text_size=(dp(700), None), halign='left')
                box.add_widget(msg)
                tm = Label(text=f"{notif.get('timestamp', '')}", color=get_color_from_hex('#555566'),
                           font_size=dp(11), size_hint_y=None, height=dp(20), halign='left')
                box.add_widget(tm)
                layout.add_widget(box)
        scroll.add_widget(layout)
        self.add_widget(scroll)
        
    def update_rect(self, instance, value):
        if hasattr(instance, 'rect'):
            instance.rect.pos = instance.pos
            instance.rect.size = instance.size


if __name__ == '__main__':
    os.system("cls")
    MainApp().run()