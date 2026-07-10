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

# Попытка импортировать логотип из файла logo.py
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
        self.alfacrm = AlfaCRMApi(self.config_manager.config)
        self.alfacrm.db = self.db
        self.notification_manager = NotificationManager(self.db)
        self.scheduler = Scheduler(self.alfacrm, self.db, self.notification_manager)
        
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
        status_box = BoxLayout(size_hint_x=0.15, spacing=dp(5))
        self.status_indicator = Label(text="•", color=get_color_from_hex('#ff4444'),
                                      font_size=dp(30), size_hint_x=None, width=dp(40))
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
        self.calendar_widget = CalendarWidget(self.db)
        self.calendar_widget.api = self.alfacrm
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
        if self.config_manager.get('username') and self.config_manager.get('password'):
            threading.Thread(target=self.test_login, daemon=True).start()
            
    def test_login(self):
        try:
            if self.alfacrm.login():
                Clock.schedule_once(lambda dt: self.update_status('Подключено', '#44ff44'))
                Clock.schedule_once(lambda dt: self.calendar_widget.build_calendar(), 0.5)
                week_start = datetime.now() - timedelta(days=datetime.now().weekday())
                week_end = week_start + timedelta(days=6)
                lessons = self.db.get_lessons_for_period(week_start.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d"))
                Clock.schedule_once(lambda dt: self.update_lesson_count(len(lessons)))
            else:
                Clock.schedule_once(lambda dt: self.update_status('Нет подключения', '#ff4444'))
        except Exception as e:
            print(f"Ошибка: {e}")
            Clock.schedule_once(lambda dt: self.update_status('Ошибка подключения', '#ff4444'))
            
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
        if hasattr(self, 'alfacrm'):
            self.alfacrm.close()


# ============================== КАЛЕНДАРЬ ==============================
class CalendarWidget(BoxLayout):
    def __init__(self, db, **kwargs):
        super().__init__(**kwargs)
        self.db = db
        self.api = None
        self.orientation = 'vertical'
        self.current_date = datetime.now()
        self.hours = list(range(8, 22))
        self.zoom_level = 1.0
        # Кеш данных
        self.week_lessons_cache = []
        self.lessons_by_day_cache = {}
        self.current_week_start_str = None
        self.current_week_end_str = None
        self.data_loaded = False
        # Ссылки на виджеты для перестройки таблицы
        self.scroll = None
        self.calendar_grid = None
        Clock.schedule_once(lambda dt: self.build_calendar(), 0.1)
        Window.bind(on_resize=self.on_window_resize)
        
    def on_window_resize(self, window, width, height):
        # При изменении размера только перестраиваем таблицу, не загружая данные
        self.rebuild_table()
        
    def build_calendar(self):
        """Полная перестройка календаря (навигация + таблица)"""
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
        
        # Масштаб
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
        
        # Прокрутка
        self.scroll = ScrollView(do_scroll_x=True, do_scroll_y=True,
                                 bar_width=dp(8), bar_color=(0.3,0.3,0.5,0.8))
        
        # Загружаем данные, если неделя изменилась
        self.load_week_lessons()
        
        # Создаём таблицу
        self.calendar_grid = GridLayout(cols=8, spacing=1, size_hint=(1, 1))
        self.build_table()
        
        self.scroll.add_widget(self.calendar_grid)
        self.add_widget(self.scroll)
        
    def rebuild_table(self):
        """Перестроить только таблицу с текущими данными (без перезагрузки)"""
        if self.calendar_grid:
            # Очищаем и перестраиваем
            self.calendar_grid.clear_widgets()
            self.build_table()
        
    def load_week_lessons(self):
        """Загрузить уроки за неделю, если неделя изменилась"""
        week_start = self.current_date - timedelta(days=self.current_date.weekday())
        week_end = week_start + timedelta(days=6)
        start_str = week_start.strftime("%Y-%m-%d")
        end_str = week_end.strftime("%Y-%m-%d")
        
        # Проверяем, изменилась ли неделя
        if (self.current_week_start_str == start_str and 
            self.current_week_end_str == end_str and 
            self.data_loaded):
            # Данные уже загружены
            return
        
        # Обновляем кеш
        self.current_week_start_str = start_str
        self.current_week_end_str = end_str
        
        if self.api:
            try:
                lessons = self.api.get_lessons_from_api(start_str, end_str)
                if lessons:
                    self.db.save_lessons(lessons)
            except Exception as e:
                print(f"Ошибка загрузки: {e}")
        
        self.week_lessons_cache = self.db.get_lessons_for_period(start_str, end_str)
        self.lessons_by_day_cache = {}
        for lesson in self.week_lessons_cache:
            day = lesson.get('date', '')
            if day:
                self.lessons_by_day_cache.setdefault(day, []).append(lesson)
        self.data_loaded = True
        
    def build_table(self):
        """Построить таблицу на основе кешированных данных"""
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
                        # Время теперь может быть в формате "HH:MM - HH:MM"
                        # Проверяем, попадает ли урок в этот час (начало в этом часе)
                        if l_time and l_time.startswith(f"{hour:02d}:"):
                            lessons_in_hour.append(l)
                
                if lessons_in_hour:
                    widget = self.create_lesson_widget(lessons_in_hour, curr_h, col_w)
                    cell.add_widget(widget)
                
                self.calendar_grid.add_widget(cell)
                    
    def create_lesson_widget(self, lessons, height, width):
        box = BoxLayout(orientation='vertical',
                        size_hint=(None, None),
                        size=(width-dp(4), height-dp(2)),
                        padding=[dp(2), dp(2), dp(2), dp(2)])
        
        if len(lessons) == 1:
            lesson = lessons[0]
            is_occupied = lesson.get('is_occupied', False)
            status = lesson.get('status', 'scheduled')
            ltype = lesson.get('type', 'unknown')
        else:
            is_occupied = True
            status = 'scheduled'
            ltype = 'multiple'
        
        # Определяем цвет фона согласно новым правилам
        # Приоритет: cancelled > trial > occupied > стандартный
        if status == 'cancelled':
            bg = (0.6, 0.1, 0.1, 0.9)          # красный
            border = (0.8, 0.2, 0.2, 1)
            text_color = (1, 0.8, 0.8, 1)
        elif ltype == 'trial':
            bg = (0.1, 0.6, 0.1, 0.9)          # зелёный
            border = (0.2, 0.8, 0.2, 1)
            text_color = (0.8, 1, 0.8, 1)
        elif is_occupied:
            bg = (0.3, 0.3, 0.3, 0.9)          # светло-серый (забронирован)
            border = (0.5, 0.5, 0.5, 1)
            text_color = (0.9, 0.9, 0.9, 1)
        else:
            bg = (0.15, 0.35, 0.65, 0.9)      # стандартный синий
            border = (0.25, 0.55, 0.85, 1)
            text_color = (1, 1, 1, 1)
        
        with box.canvas.before:
            Color(*bg)
            box.rect = RoundedRectangle(size=box.size, pos=box.pos, radius=[(dp(4), dp(4))])
            Color(*border)
            box.border = RoundedRectangle(size=box.size, pos=box.pos, radius=[(dp(4), dp(4))])
        box.bind(size=self.update_rect, pos=self.update_rect)
        
        if len(lessons) == 1:
            l = lessons[0]
            client = l.get('client', '')
            
            # Статус-символы
            status_symbols = {'scheduled': '(P)', 'completed': '(C)', 'cancelled': '(X)'}
            sym = status_symbols.get(status, '')
            if sym:
                top_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=height*0.5)
                status_lbl = Label(text=sym, color=text_color, font_size=dp(10), bold=True,
                                   size_hint_x=None, width=dp(30), halign='center')
                top_row.add_widget(status_lbl)
                name_lbl = Label(text=client, color=text_color, font_size=dp(9), bold=True,
                                 size_hint_x=1, text_size=(width-dp(30), None), halign='left', shorten=True)
                top_row.add_widget(name_lbl)
                box.add_widget(top_row)
            else:
                name_lbl = Label(text=client, color=text_color, font_size=dp(9), bold=True,
                                 size_hint_y=None, height=height*0.5,
                                 text_size=(width-dp(10), None), halign='left', shorten=True)
                box.add_widget(name_lbl)
            
            # Отображаем время (диапазон)
            time_display = l.get('time', '')
            if not time_display:
                time_display = l.get('time_start', '')
            time_lbl = Label(text=time_display, color=(0.7,0.7,0.8,1),
                             font_size=dp(8), size_hint_y=None, height=height*0.5,
                             text_size=(width-dp(10), None), halign='left')
            box.add_widget(time_lbl)
            box.lesson = l
        else:
            names = []
            for l in lessons[:2]:
                names.append(l.get('client', '?'))
            if len(lessons) > 2:
                names.append(f"+{len(lessons)-2}")
            lbl = Label(text=", ".join(names), color=text_color, font_size=dp(9),
                        size_hint_y=None, height=height-dp(4),
                        text_size=(width-dp(10), None), halign='center', valign='middle')
            box.add_widget(lbl)
            box.lessons = lessons
        
        box.bind(on_touch_down=self._on_lesson_click)
        return box
        
    def _on_lesson_click(self, instance, touch):
        if instance.collide_point(*touch.pos):
            if hasattr(instance, 'lesson'):
                self.show_lesson_details(instance.lesson)
            elif hasattr(instance, 'lessons'):
                self.show_lesson_details(instance.lessons[0])
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
        info = f"""
Клиент: {lesson.get('client', 'Не указан')}
Статус: {status_names.get(lesson.get('status', ''), 'Неизвестен')}
Тип: {type_names.get(lesson.get('type', ''), 'Неизвестен')}
Дата: {lesson.get('date', 'Не указана')}
Время: {lesson.get('time', 'Не указано')}
Комментарий: {lesson.get('comment', 'Нет')}
Преподаватель: {lesson.get('teacher', 'Не указан')}
Кабинет: {lesson.get('room', 'Не указан')}
        """
        info_lbl = Label(text=info, color=get_color_from_hex('#ccccdd'),
                         font_size=dp(14), size_hint_y=None, height=dp(220),
                         halign='left', valign='top', text_size=(dp(400), None))
        content.add_widget(info_lbl)
        
        btn_box = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        customer_id = lesson.get('customer_id')
        if customer_id:
            lesson_url = f"https://rtschool.s20.online/teacher/1/customer/view?id={customer_id}"
        else:
            lesson_id = lesson.get('id')
            if lesson_id:
                lesson_url = f"https://rtschool.s20.online/teacher/1/lesson/view?id={lesson_id}"
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
            self.rebuild_table()  # только перестройка таблицы
            
    def update_rect(self, instance, value):
        for attr in ['rect', 'border']:
            if hasattr(instance, attr):
                getattr(instance, attr).pos = instance.pos
                getattr(instance, attr).size = instance.size
        if hasattr(instance, 'children'):
            for child in instance.children:
                self.update_rect(child, value)
                
    def prev_week(self, instance):
        self.current_date -= timedelta(days=7)
        self.data_loaded = False  # сброс флага, чтобы загрузить новые данные
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
        
        # Группа: Подключение
        group1 = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(220), spacing=dp(10))
        group1_label = Label(text="Подключение к CRM", color=get_color_from_hex('#66ccff'),
                             font_size=dp(16), bold=True, size_hint_y=None, height=dp(30))
        group1.add_widget(group1_label)
        
        fields = [
            ('URL сайта:', 'site_url'),
            ('Логин:', 'username'),
            ('Пароль:', 'password')
        ]
        self.entries = {}
        for label_text, key in fields:
            container = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
            label = Label(text=label_text, color=get_color_from_hex('#888899'),
                          font_size=dp(13), size_hint_x=0.25, halign='right')
            container.add_widget(label)
            is_pwd = 'пароль' in label_text.lower() or 'password' in label_text.lower()
            entry = TextInput(text=str(self.app.config_manager.get(key, '')),
                              size_hint_x=0.75, height=dp(40),
                              background_color=(0.12,0.12,0.18,1),
                              foreground_color=(1,1,1,1),
                              cursor_color=(0.3,0.6,1,1),
                              password=is_pwd,
                              font_size=dp(13), padding=[dp(10), dp(5)])
            container.add_widget(entry)
            self.entries[key] = entry
            group1.add_widget(container)
        content.add_widget(group1)
        
        # Разделитель
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
        self.entries['check_interval_hours'] = entry
        group2.add_widget(container)
        
        # Автозапуск
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
        
    def toggle_auto_start(self, instance):
        current = self.app.config_manager.get('auto_start', False)
        new_val = not current
        self.app.config_manager.set('auto_start', new_val)
        instance.text = "Вкл" if new_val else "Выкл"
        instance.background_color = (0.15,0.4,0.15,1) if new_val else (0.3,0.3,0.3,1)
        
    def save_settings(self, instance):
        for key, entry in self.entries.items():
            self.app.config_manager.set(key, entry.text)
        try:
            interval = int(self.entries['check_interval_hours'].text)
            if interval < 1: interval = 1
            self.app.config_manager.set('check_interval_hours', interval)
            self.app.scheduler.set_check_interval(interval)
        except: pass
        self.status_label.text = "Настройки сохранены"
        self.status_label.color = get_color_from_hex('#66cc66')
        
    def test_connection(self, instance):
        self.status_label.text = "Проверка подключения..."
        self.status_label.color = get_color_from_hex('#cccc00')
        def test():
            try:
                for key, entry in self.entries.items():
                    self.app.config_manager.set(key, entry.text)
                api = AlfaCRMApi(self.app.config_manager.config)
                api.db = self.app.db
                api.setup_driver()
                success = api.login()
                api.close()
                if success:
                    Clock.schedule_once(lambda dt: self.update_status("Подключение успешно", get_color_from_hex('#66cc66')))
                else:
                    Clock.schedule_once(lambda dt: self.update_status("Ошибка подключения", get_color_from_hex('#ff6666')))
            except Exception as e:
                Clock.schedule_once(lambda dt: self.update_status(f"Ошибка: {str(e)[:50]}", get_color_from_hex('#ff6666')))
        threading.Thread(target=test).start()
        
    def update_status(self, text, color):
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
    MainApp().run()