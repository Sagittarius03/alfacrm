# -*- coding: utf-8 -*-
"""
AlfaCRM Automation - PyQt5 версия с Playwright
"""

import sys
import os
import asyncio
import threading
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QPushButton, QLineEdit, QTextEdit, QScrollArea,
    QFrame, QMessageBox, QProgressDialog, QGridLayout,
    QGroupBox, QCheckBox, QSpinBox, QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QColor, QPalette

from alfacrm_api_async import AlfaCRMApiAsync
from database import SyncDatabase as Database
from notification_manager import NotificationManager
from scheduler import Scheduler
from config_manager import ConfigManager


# ============================== ДИАЛОГ 2FA ==============================
class TwoFADialog(QDialog):
    """Диалог для ввода кода 2FA"""
    def __init__(self, crm_type: str, parent=None):
        super().__init__(parent)
        self.crm_type = crm_type
        self.code = None
        self.setWindowTitle(f"2FA - {crm_type}")
        self.setModal(True)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setMinimumWidth(400)
        self.setup_ui()
        self.raise_()
        self.activateWindow()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        info = QLabel(f"🔐 Требуется код подтверждения для {self.crm_type}")
        info.setStyleSheet("font-size: 16px; font-weight: bold; color: #66ccff;")
        layout.addWidget(info)
        
        info2 = QLabel("Введите код из письма или приложения аутентификации:")
        info2.setStyleSheet("color: #888;")
        layout.addWidget(info2)
        
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Введите 6-значный код...")
        self.code_input.setMaxLength(6)
        self.code_input.setStyleSheet("""
            QLineEdit {
                font-size: 20px;
                padding: 10px;
                background-color: #1a1a2e;
                color: white;
                border: 2px solid #2d4059;
                border-radius: 5px;
            }
            QLineEdit:focus {
                border-color: #4a7a9c;
            }
        """)
        layout.addWidget(self.code_input)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #333;
                color: white;
                padding: 8px 25px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #444;
            }
        """)
        btn_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("Подтвердить")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d4059;
                color: white;
                padding: 8px 25px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3d5a80;
            }
        """)
        ok_btn.clicked.connect(self.on_ok)
        ok_btn.setDefault(True)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)
        self.code_input.setFocus()
    
    def on_ok(self):
        code = self.code_input.text().strip()
        if code and len(code) >= 4:
            self.code = code
            self.accept()
        else:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, введите код подтверждения (минимум 4 символа)")


# ============================== ОКНО ДЕТАЛЕЙ УРОКА ==============================
class LessonDetailsDialog(QDialog):
    def __init__(self, lesson: Dict, db, api_instances, parent=None):
        super().__init__(parent)
        self.lesson = lesson
        self.db = db
        self.api_instances = api_instances
        self.setWindowTitle(f"Урок {lesson.get('time', '')}")
        self.setMinimumSize(550, 450)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel(f"📚 Урок {self.lesson.get('time', '')}")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff;")
        layout.addWidget(title)
        
        info = QTextEdit()
        info.setReadOnly(True)
        info.setMaximumHeight(200)
        
        status_names = {
            'scheduled': 'Запланирован',
            'cancelled': 'Отменён',
            'completed': 'Проведён',
            'rescheduled': 'Перенос'
        }
        
        group_name = self.lesson.get('group_name', '')
        lines = [
            f"CRM: {self.lesson.get('crm_type', 'неизвестно').capitalize()}",
            f"Статус: {status_names.get(self.lesson.get('status', ''), 'Неизвестен')}",
            f"Тип: {self.lesson.get('type', 'неизвестен')}",
            f"Дата: {self.lesson.get('date', 'Не указана')}",
            f"Время: {self.lesson.get('time', 'Не указано')}",
            f"Предмет: {self.lesson.get('subject', 'Не указан')}",
        ]
        
        if group_name:
            lines.insert(2, f"Группа: {group_name}")
        
        topic = self.lesson.get('topic', '')
        if topic:
            lines.insert(4, f"Тема: {topic}")
        
        comment = self.lesson.get('comment', '').strip()
        if comment:
            lines.append(f"Комментарий: {comment}")
        
        info.setText("\n".join(lines))
        layout.addWidget(info)
        
        students_label = QLabel("👨‍🎓 Ученики:")
        students_label.setStyleSheet("font-weight: bold; color: #66ccff; margin-top: 10px;")
        layout.addWidget(students_label)
        
        students = self.lesson.get('students', [])
        if students:
            students_text = QTextEdit()
            students_text.setReadOnly(True)
            students_text.setMaximumHeight(150)
            
            for s in students:
                name = s.get('name', 'Без имени')
                status = s.get('status_on_lesson', '')
                balance = s.get('balance')
                line = f"  • {name}"
                if status:
                    line += f" [{status}]"
                if balance is not None:
                    line += f" (остаток: {balance} ур.)"
                students_text.append(line)
            
            layout.addWidget(students_text)
        else:
            no_students = QLabel("Нет учеников")
            no_students.setStyleSheet("color: #888;")
            layout.addWidget(no_students)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)


# ============================== ВКЛАДКА КАЛЕНДАРЯ ==============================
class CalendarTab(QWidget):
    def __init__(self, db, api_instances):
        super().__init__()
        self.db = db
        self.api_instances = api_instances
        self.current_date = datetime.now()
        self.hours = list(range(8, 22))
        self.lessons_by_day = {}
        self.zoom_level = 1.0
        
        self.setup_ui()
        self.load_lessons()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        nav_layout = QHBoxLayout()
        
        prev_btn = QPushButton("◀")
        prev_btn.setFixedSize(40, 40)
        prev_btn.clicked.connect(self.prev_week)
        nav_layout.addWidget(prev_btn)
        
        self.week_label = QLabel()
        self.week_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        nav_layout.addWidget(self.week_label)
        
        today_btn = QPushButton("Сегодня")
        today_btn.clicked.connect(self.go_today)
        nav_layout.addWidget(today_btn)
        
        nav_layout.addStretch()
        
        zoom_label = QLabel("Масштаб:")
        zoom_label.setStyleSheet("color: #888;")
        nav_layout.addWidget(zoom_label)
        
        zoom_out = QPushButton("−")
        zoom_out.setFixedSize(35, 35)
        zoom_out.clicked.connect(lambda: self.zoom(-0.1))
        nav_layout.addWidget(zoom_out)
        
        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet("color: #888; min-width: 40px;")
        nav_layout.addWidget(self.zoom_label)
        
        zoom_in = QPushButton("+")
        zoom_in.setFixedSize(35, 35)
        zoom_in.clicked.connect(lambda: self.zoom(0.1))
        nav_layout.addWidget(zoom_in)
        
        next_btn = QPushButton("▶")
        next_btn.setFixedSize(40, 40)
        next_btn.clicked.connect(self.next_week)
        nav_layout.addWidget(next_btn)
        
        layout.addLayout(nav_layout)
        
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.table.verticalHeader().setDefaultSectionSize(70)
        
        layout.addWidget(self.table)
        self.update_week_label()
    
    def update_week_label(self):
        week_start = self.current_date - timedelta(days=self.current_date.weekday())
        week_end = week_start + timedelta(days=6)
        self.week_label.setText(
            f"{week_start.strftime('%d.%m.%Y')} — {week_end.strftime('%d.%m.%Y')}"
        )
    
    def load_lessons(self):
        week_start = self.current_date - timedelta(days=self.current_date.weekday())
        week_end = week_start + timedelta(days=6)
        start_str = week_start.strftime("%Y-%m-%d")
        end_str = week_end.strftime("%Y-%m-%d")
        
        lessons = self.db.get_lessons_for_period(start_str, end_str)
        
        self.lessons_by_day = {}
        for lesson in lessons:
            day = lesson.get('date', '')
            if day:
                if day not in self.lessons_by_day:
                    self.lessons_by_day[day] = []
                self.lessons_by_day[day].append(lesson)
        
        self.build_table()
    
    def build_table(self):
        week_start = self.current_date - timedelta(days=self.current_date.weekday())
        
        rows = len(self.hours) + 1
        cols = 8
        
        self.table.setRowCount(rows)
        self.table.setColumnCount(cols)
        
        days_short = ['Час', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС']
        
        self.table.setColumnWidth(0, 100)
        
        for col, day in enumerate(days_short):
            item = QTableWidgetItem(day)
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(QColor(26, 26, 46))
            item.setForeground(QColor(136, 136, 153))
            self.table.setHorizontalHeaderItem(col, item)
        
        for row, hour in enumerate(self.hours):
            item = QTableWidgetItem(f"{hour:02d}:00")
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item.setBackground(QColor(26, 26, 46))
            item.setForeground(QColor(85, 85, 102))
            self.table.setVerticalHeaderItem(row, item)
            self.table.setItem(row, 0, item)
        
        for row, hour in enumerate(self.hours):
            for col in range(1, 8):
                day_date = week_start + timedelta(days=col - 1)
                date_str = day_date.strftime("%Y-%m-%d")
                
                lessons_in_hour = []
                if date_str in self.lessons_by_day:
                    for lesson in self.lessons_by_day[date_str]:
                        l_time = lesson.get('time', '')
                        if l_time:
                            try:
                                time_match = re.match(r'(\d{1,2}):(\d{2})', l_time)
                                if time_match:
                                    lesson_hour = int(time_match.group(1))
                                    if lesson_hour == hour:
                                        lessons_in_hour.append(lesson)
                            except:
                                if l_time.startswith(f"{hour:02d}:"):
                                    lessons_in_hour.append(lesson)
                
                if lessons_in_hour:
                    widget = self.create_lesson_widget(lessons_in_hour)
                    self.table.setCellWidget(row, col, widget)
                else:
                    item = QTableWidgetItem("")
                    item.setBackground(QColor(18, 18, 26))
                    self.table.setItem(row, col, item)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        for col in range(1, 8):
            header.setSectionResizeMode(col, QHeaderView.Stretch)
        
        self.table.verticalHeader().setDefaultSectionSize(70)
    
    def create_lesson_widget(self, lessons):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        for lesson in lessons:
            btn = QPushButton(self.get_lesson_text(lesson))
            btn.setStyleSheet(self.get_lesson_style(lesson))
            btn.setMinimumHeight(30)
            btn.clicked.connect(lambda checked, l=lesson: self.show_lesson_details(l))
            layout.addWidget(btn)
        
        return widget
    
    def get_lesson_text(self, lesson):
        status = lesson.get('status', 'scheduled')
        time_str = lesson.get('time', '')
        lesson_type = lesson.get('type', '')
        group_name = lesson.get('group_name', '')
        
        if lesson_type == 'group' and group_name:
            client = f"👥 {group_name}"
        else:
            client = lesson.get('client', '')
            if len(client) > 25:
                client = client[:23] + "..."
        
        if status == 'cancelled':
            prefix = "✕"
        elif status == 'completed':
            prefix = "✓"
        elif status == 'rescheduled':
            prefix = "↪"
        else:
            prefix = "●"
        
        type_icon = ""
        if lesson_type == 'group':
            type_icon = ""
        elif lesson_type == 'trial':
            type_icon = "🎯 "
        elif lesson_type == 'individual':
            type_icon = "👤 "
        
        if time_str:
            time_part = time_str.split('-')[0].strip() if '-' in time_str else time_str
            return f"{prefix} {time_part} {type_icon}{client}"
        else:
            return f"{prefix} {type_icon}{client}"
    
    def get_lesson_style(self, lesson):
        status = lesson.get('status', 'scheduled')
        ltype = lesson.get('type', 'unknown')
        
        if status == 'rescheduled':
            bg = "#3d3d3d"
            color = "#aaaaaa"
        elif ltype == 'trial':
            bg = "#4a4a4a"
            color = "#cccccc"
        elif status == 'cancelled':
            bg = "#2a2a2a"
            color = "#888888"
        elif status == 'completed':
            bg = "#1a4a1a"
            color = "#66ff66"
        else:
            bg = "#1a2a4a"
            color = "#66ccff"
        
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                border: none;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
                text-align: left;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3d5a80;
            }}
        """
    
    def show_lesson_details(self, lesson):
        dialog = LessonDetailsDialog(lesson, self.db, self.api_instances, self.window())
        dialog.exec_()
    
    def on_cell_double_clicked(self, row, col):
        widget = self.table.cellWidget(row, col)
        if widget:
            for child in widget.children():
                if isinstance(child, QPushButton):
                    child.click()
                    break
    
    def zoom(self, delta):
        self.zoom_level = max(0.5, min(2.0, self.zoom_level + delta))
        self.zoom_label.setText(f"{int(self.zoom_level * 100)}%")
        new_height = int(70 * self.zoom_level)
        self.table.verticalHeader().setDefaultSectionSize(max(35, new_height))
        self.table.resizeRowsToContents()
    
    def prev_week(self):
        self.current_date -= timedelta(days=7)
        self.update_week_label()
        self.load_lessons()
    
    def next_week(self):
        self.current_date += timedelta(days=7)
        self.update_week_label()
        self.load_lessons()
    
    def go_today(self):
        self.current_date = datetime.now()
        self.update_week_label()
        self.load_lessons()


# ============================== ВКЛАДКА УВЕДОМЛЕНИЙ ==============================
class NotificationsTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setup_ui()
        self.load_notifications()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        title = QLabel("🔔 Уведомления")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        layout.addWidget(title)
        
        self.notifications_list = QTextEdit()
        self.notifications_list.setReadOnly(True)
        self.notifications_list.setStyleSheet("""
            QTextEdit {
                background-color: #0f0f1a;
                color: #ccc;
                border: 1px solid #222;
                border-radius: 5px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.notifications_list)
    
    def load_notifications(self):
        notifications = self.db.get_notifications(100)
        if notifications:
            text = ""
            for notif in reversed(notifications):
                timestamp = notif.get('timestamp', '')
                message = notif.get('message', '')
                text += f"[{timestamp}] {message}\n\n"
            self.notifications_list.setText(text)
        else:
            self.notifications_list.setText("Нет уведомлений")


# ============================== ВКЛАДКА НАСТРОЕК ==============================
class SettingsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(15)
        
        profiles_group = QGroupBox("Профили CRM")
        profiles_group.setStyleSheet("""
            QGroupBox {
                color: #66ccff;
                font-weight: bold;
                border: 1px solid #333;
                border-radius: 5px;
                padding-top: 15px;
            }
            QGroupBox::title { subcontrol-origin: margin; padding: 0 10px; }
        """)
        profiles_layout = QVBoxLayout(profiles_group)
        
        self.profile_widgets = []
        profiles = self.main_window.config_manager.get_profiles()
        
        for profile in profiles:
            widget = self.create_profile_widget(profile)
            profiles_layout.addWidget(widget)
        
        add_btn = QPushButton("+ Добавить профиль")
        add_btn.clicked.connect(self.add_profile)
        profiles_layout.addWidget(add_btn)
        
        content_layout.addWidget(profiles_group)
        
        schedule_group = QGroupBox("Расписание и уведомления")
        schedule_group.setStyleSheet(profiles_group.styleSheet())
        schedule_layout = QGridLayout(schedule_group)
        
        label = QLabel("Интервал проверки (часы):")
        label.setStyleSheet("color: #888;")
        schedule_layout.addWidget(label, 0, 0)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setMinimum(1)
        self.interval_spin.setMaximum(24)
        interval = self.main_window.config_manager.get('check_interval_hours', 1)
        self.interval_spin.setValue(int(interval))
        schedule_layout.addWidget(self.interval_spin, 0, 1)
        
        self.auto_start_check = QCheckBox("Автозапуск при старте")
        self.auto_start_check.setStyleSheet("color: #888;")
        auto_start = self.main_window.config_manager.get('auto_start', False)
        self.auto_start_check.setChecked(auto_start)
        schedule_layout.addWidget(self.auto_start_check, 1, 0, 1, 2)
        
        content_layout.addWidget(schedule_group)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("💾 Сохранить")
        save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(save_btn)
        
        test_btn = QPushButton("🔌 Проверить подключение")
        test_btn.clicked.connect(self.test_connection)
        btn_layout.addWidget(test_btn)
        
        btn_layout.addStretch()
        content_layout.addLayout(btn_layout)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #66cc66;")
        content_layout.addWidget(self.status_label)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
    
    def create_profile_widget(self, profile):
        widget = QWidget()
        widget.setStyleSheet("""
            QWidget {
                background-color: #1a1a2e;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        layout = QGridLayout(widget)
        
        crm_label = QLabel(profile.get('crm_type', 'rts').upper())
        crm_label.setStyleSheet("color: #88ccff; font-weight: bold; font-size: 14px;")
        layout.addWidget(crm_label, 0, 0, 1, 2)
        
        fields = [
            ('URL:', 'site_url'),
            ('Логин:', 'username'),
            ('Пароль:', 'password')
        ]
        
        entries = {}
        for row, (label_text, key) in enumerate(fields, start=1):
            label = QLabel(label_text)
            label.setStyleSheet("color: #888;")
            layout.addWidget(label, row, 0)
            
            entry = QLineEdit(str(profile.get(key, '')))
            if 'пароль' in label_text.lower() or 'password' in label_text.lower():
                entry.setEchoMode(QLineEdit.Password)
            layout.addWidget(entry, row, 1)
            entries[key] = entry
        
        entries['crm_type'] = QLineEdit(profile.get('crm_type', 'rts'))
        entries['crm_type'].hide()
        
        widget.entries = entries
        return widget
    
    def add_profile(self):
        widget = self.create_profile_widget({
            'site_url': 'https://rtschool.s20.online',
            'username': '',
            'password': '',
            'crm_type': 'rts'
        })
        parent_layout = widget.parent().layout()
        if parent_layout:
            parent_layout.insertWidget(parent_layout.count() - 1, widget)
    
    def save_settings(self):
        profiles = []
        parent = self.profile_widgets[0].parent() if self.profile_widgets else None
        if parent:
            for i in range(parent.layout().count()):
                widget = parent.layout().itemAt(i).widget()
                if widget and hasattr(widget, 'entries'):
                    entries = widget.entries
                    profile = {
                        'site_url': entries['site_url'].text(),
                        'username': entries['username'].text(),
                        'password': entries['password'].text(),
                        'crm_type': entries['crm_type'].text() or 'rts'
                    }
                    if profile['site_url'] and profile['username']:
                        profiles.append(profile)
        
        self.main_window.config_manager.save_profiles(profiles)
        self.main_window.config_manager.set('check_interval_hours', self.interval_spin.value())
        self.main_window.config_manager.set('auto_start', self.auto_start_check.isChecked())
        
        self.main_window.api_instances = []
        self.main_window.load_profiles()
        
        self.status_label.setText("✅ Настройки сохранены")
    
    def test_connection(self):
        self.status_label.setText("⏳ Проверка подключения...")
        
        def test():
            try:
                for api in self.main_window.api_instances:
                    if not api.login_sync():
                        self.update_status("❌ Ошибка подключения", '#ff6666')
                        return
                self.update_status("✅ Подключение успешно", '#66cc66')
            except Exception as e:
                self.update_status(f"❌ Ошибка: {str(e)[:50]}", '#ff6666')
        
        threading.Thread(target=test, daemon=True).start()
    
    def update_status(self, text, color):
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)


# ============================== РАБОЧИЙ ПОТОК ДЛЯ ЗАГРУЗКИ ==============================
class LoaderThread(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    need_2fa = pyqtSignal(str)
    
    def __init__(self, api_instances, db, start_date, end_date):
        super().__init__()
        self.api_instances = api_instances
        self.db = db
        self.start_date = start_date
        self.end_date = end_date
        self._running = True
        self._2fa_code = None
        self._2fa_event = threading.Event()
        
    def stop(self):
        self._running = False
        self._2fa_event.set()
        
    def set_2fa_code(self, code: str):
        self._2fa_code = code
        self._2fa_event.set()
    
    def wait_for_2fa(self, timeout: int = 120) -> Optional[str]:
        if self._2fa_event.wait(timeout):
            return self._2fa_code
        return None
    
    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                lessons = loop.run_until_complete(self._load_lessons())
                if self._running:
                    self.finished.emit(lessons)
            finally:
                loop.close()
        except Exception as e:
            if self._running:
                self.error.emit(str(e))
    
    async def _load_lessons(self):
        all_lessons = []
        total_apis = len(self.api_instances)
        
        for idx, api in enumerate(self.api_instances):
            if not self._running:
                break
            
            try:
                self.progress.emit(idx, total_apis, f"Загрузка {api.crm_type}...")
                
                if not api.is_logged_in:
                    success = await api.login_async()
                    
                    if not success and api.is_2fa_required():
                        self.need_2fa.emit(api.crm_type)
                        
                        code = await asyncio.get_event_loop().run_in_executor(
                            None, self.wait_for_2fa, 120
                        )
                        
                        if code:
                            success = await api.continue_login_with_2fa(code)
                        else:
                            self.progress.emit(idx + 1, total_apis, f"⏰ Таймаут 2FA для {api.crm_type}")
                            continue
                    
                    if not success:
                        self.progress.emit(idx + 1, total_apis, f"❌ Ошибка входа для {api.crm_type}")
                        continue
                
                lessons = await api.get_lessons_from_api_async(self.start_date, self.end_date)
                
                if lessons:
                    all_lessons.extend(lessons)
                    for lesson in lessons:
                        api.save_lesson_relations_sync(
                            lesson, lesson.get('students', []), 
                            lesson.get('group_id')
                        )
                        
                self.progress.emit(idx + 1, total_apis, f"{api.crm_type}: {len(lessons) if lessons else 0} уроков")
                
            except Exception as e:
                print(f"Ошибка загрузки из {api.crm_type}: {e}")
                import traceback
                traceback.print_exc()
                self.progress.emit(idx + 1, total_apis, f"Ошибка: {api.crm_type}")
        
        return all_lessons


# ============================== ГЛАВНОЕ ОКНО ==============================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AlfaCRM Automation")
        self.setMinimumSize(1200, 800)
        
        self.db = Database()
        self.config_manager = ConfigManager(db=self.db)
        self.api_instances = []
        self.load_profiles()
        self.notification_manager = NotificationManager(self.db)
        self.scheduler = Scheduler(
            self.api_instances[0] if self.api_instances else None,
            self.db,
            self.notification_manager
        )
        
        self.is_loading = False
        self.loader_thread = None
        self.lessons_cache = []
        
        self.setup_ui()
        self.setup_styles()
        
        if self.config_manager.get('auto_start', False):
            self.scheduler.start()
        
        QTimer.singleShot(2000, self.check_connection)
    
    def load_profiles(self):
        profiles = self.config_manager.get_profiles()
        for profile in profiles:
            api = AlfaCRMApiAsync(profile, crm_type=profile.get('crm_type', 'rts'))
            api.db = self.db
            self.api_instances.append(api)
        if not self.api_instances:
            default_profile = {
                'site_url': 'https://rtschool.s20.online',
                'username': '',
                'password': '',
                'crm_type': 'rts'
            }
            api = AlfaCRMApiAsync(default_profile, crm_type='rts')
            api.db = self.db
            self.api_instances.append(api)
    
    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet("QFrame { background-color: #1a1a2e; border: none; }")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 5, 15, 5)
        
        title = QLabel("🚀 AlfaCRM Automation")
        title.setStyleSheet("color: white; font-size: 20px; font-weight: bold;")
        header_layout.addWidget(title)
        
        self.status_indicator = QLabel("🔴")
        self.status_indicator.setStyleSheet("font-size: 20px;")
        header_layout.addWidget(self.status_indicator)
        
        self.status_text = QLabel("Нет подключения")
        self.status_text.setStyleSheet("color: #888; font-size: 14px;")
        header_layout.addWidget(self.status_text)
        
        header_layout.addStretch()
        
        self.lesson_count = QLabel("0 уроков")
        self.lesson_count.setStyleSheet("color: #666; font-size: 14px;")
        header_layout.addWidget(self.lesson_count)
        
        self.refresh_btn = QPushButton("🔄 Обновить")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d4059;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3d5a80; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        self.refresh_btn.clicked.connect(self.load_lessons)
        header_layout.addWidget(self.refresh_btn)
        
        main_layout.addWidget(header)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background-color: #0f0f1a; }
            QTabBar::tab {
                background-color: #1a1a2e;
                color: #888;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected { background-color: #2d4059; color: white; }
            QTabBar::tab:hover { background-color: #2d4059; }
        """)
        
        self.calendar_tab = CalendarTab(self.db, self.api_instances)
        self.tabs.addTab(self.calendar_tab, "📅 Календарь")
        
        self.notifications_tab = NotificationsTab(self.db)
        self.tabs.addTab(self.notifications_tab, "🔔 Уведомления")
        
        self.settings_tab = SettingsTab(self)
        self.tabs.addTab(self.settings_tab, "⚙️ Настройки")
        
        main_layout.addWidget(self.tabs)
        
        footer = QFrame()
        footer.setFixedHeight(30)
        footer.setStyleSheet("QFrame { background-color: #1a1a2e; border: none; }")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(15, 0, 15, 0)
        
        info = QLabel("Двойной клик по уроку – подробности | Масштаб +/-")
        info.setStyleSheet("color: #444; font-size: 11px;")
        footer_layout.addWidget(info)
        
        main_layout.addWidget(footer)
    
    def setup_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #0f0f1a; }
            QLabel { color: #ccc; }
            QLineEdit, QTextEdit {
                background-color: #1a1a2e;
                color: #ccc;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 5px;
            }
            QLineEdit:focus, QTextEdit:focus { border-color: #4a7a9c; }
            QTableWidget {
                background-color: #0f0f1a;
                color: #ccc;
                gridline-color: #222;
                selection-background-color: #2d4059;
            }
            QTableWidget::item { padding: 8px 5px; }
            QHeaderView::section {
                background-color: #1a1a2e;
                color: #888;
                padding: 8px 5px;
                border: none;
                font-weight: bold;
            }
            QPushButton {
                background-color: #2d4059;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3d5a80; }
            QPushButton:pressed { background-color: #1a2a3e; }
            QScrollBar:vertical {
                background-color: #1a1a2e;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background-color: #2d4059;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QProgressDialog { background-color: #0f0f1a; color: #ccc; }
        """)
    
    def check_connection(self):
        for api in self.api_instances:
            if api.config.get('username'):
                try:
                    if api.login_sync():
                        self.update_status('Подключено', 'green')
                        self.load_lessons()
                        return
                except Exception as e:
                    print(f"Ошибка входа: {e}")
        
        self.update_status('Нет подключения', 'red')
    
    def update_status(self, text, color):
        colors = {'green': '#44ff44', 'red': '#ff4444', 'orange': '#ffaa44', 'blue': '#44aaff'}
        hex_color = colors.get(color, '#888')
        self.status_text.setText(text)
        self.status_text.setStyleSheet(f"color: {hex_color}; font-size: 14px;")
        self.status_indicator.setText("🟢" if color == 'green' else "🔴")
    
    def show_2fa_dialog(self, crm_type):
        """Показывает диалог для ввода 2FA"""
        dialog = TwoFADialog(crm_type, self)
        
        def show():
            if dialog.exec_() == QDialog.Accepted and dialog.code:
                if self.loader_thread:
                    self.loader_thread.set_2fa_code(dialog.code)
                for api in self.api_instances:
                    if api.crm_type == crm_type:
                        api.set_2fa_code(dialog.code)
                        break
            else:
                if self.loader_thread:
                    self.loader_thread.set_2fa_code("")
        
        QTimer.singleShot(0, show)
    
    def load_lessons(self):
        if self.is_loading:
            return
        
        self.is_loading = True
        self.refresh_btn.setEnabled(False)
        self.update_status('Загрузка...', 'blue')
        
        self.progress = QProgressDialog("Загрузка уроков...", "Отмена", 0, 100, self)
        self.progress.setWindowModality(Qt.WindowModal)
        self.progress.setMinimumDuration(0)
        self.progress.canceled.connect(self.cancel_loading)
        self.progress.show()
        
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_end = week_start + timedelta(days=6)
        start_str = week_start.strftime("%Y-%m-%d")
        end_str = week_end.strftime("%Y-%m-%d")
        
        self.loader_thread = LoaderThread(
            self.api_instances,
            self.db,
            start_str,
            end_str
        )
        self.loader_thread.progress.connect(self.on_loader_progress)
        self.loader_thread.finished.connect(self.on_loader_finished)
        self.loader_thread.error.connect(self.on_loader_error)
        self.loader_thread.need_2fa.connect(self.show_2fa_dialog)
        
        self.loader_thread.start()
    
    def cancel_loading(self):
        if self.loader_thread:
            self.loader_thread.stop()
            self.loader_thread.wait(1000)
        self.is_loading = False
        self.refresh_btn.setEnabled(True)
        self.progress.close()
        self.update_status('Отменено', 'orange')
    
    def on_loader_progress(self, current, total, status):
        if total > 0:
            progress = int((current / total) * 100)
            self.progress.setValue(progress)
        self.progress.setLabelText(status)
        self.status_text.setText(f"Загрузка: {status}")
    
    def on_loader_finished(self, lessons):
        self.is_loading = False
        self.refresh_btn.setEnabled(True)
        self.progress.close()
        
        self.lessons_cache = lessons
        self.lesson_count.setText(f"{len(lessons)} уроков")
        
        self.calendar_tab.load_lessons()
        
        self.update_status('Подключено', 'green')
        
        if lessons:
            QMessageBox.information(self, "Загрузка завершена", f"Загружено {len(lessons)} уроков")
    
    def on_loader_error(self, error):
        self.is_loading = False
        self.refresh_btn.setEnabled(True)
        self.progress.close()
        self.update_status('Ошибка', 'red')
        QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить уроки:\n{error}")
    
    def closeEvent(self, event):
        print("🛑 Завершение приложения...")
        
        if hasattr(self, 'scheduler'):
            try:
                self.scheduler.stop()
            except Exception as e:
                print(f"Ошибка остановки планировщика: {e}")
        
        if self.loader_thread:
            try:
                self.loader_thread.stop()
                self.loader_thread.wait(2000)
            except Exception as e:
                print(f"Ошибка остановки потока: {e}")
        
        for api in self.api_instances:
            try:
                api.close_sync()
            except Exception as e:
                print(f"Ошибка закрытия {api.crm_type}: {e}")
        
        print("✅ Приложение завершено")
        event.accept()


# ============================== ЗАПУСК ==============================
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(15, 15, 26))
    palette.setColor(QPalette.WindowText, QColor(204, 204, 204))
    palette.setColor(QPalette.Base, QColor(26, 26, 46))
    palette.setColor(QPalette.AlternateBase, QColor(20, 20, 36))
    palette.setColor(QPalette.ToolTipBase, QColor(26, 26, 46))
    palette.setColor(QPalette.ToolTipText, QColor(204, 204, 204))
    palette.setColor(QPalette.Text, QColor(204, 204, 204))
    palette.setColor(QPalette.Button, QColor(26, 26, 46))
    palette.setColor(QPalette.ButtonText, QColor(204, 204, 204))
    palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.Highlight, QColor(45, 64, 89))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()