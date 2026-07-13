# database.py - Полная перезапись
# -*- coding: utf-8 -*-
import sqlite3
import json
from datetime import datetime, timedelta
from contextlib import contextmanager

class Database:
    def __init__(self, db_path='alfacrm_data.db'):
        self.db_path = db_path
        self.init_db()
        
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
            
    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица уроков
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY,
                    date TEXT,
                    time TEXT,
                    client TEXT,
                    subject TEXT,
                    comment TEXT,
                    status TEXT,
                    link TEXT,
                    teacher TEXT,
                    room TEXT,
                    type TEXT,
                    is_occupied INTEGER,
                    customer_id TEXT,
                    crm_type TEXT,
                    site_url TEXT,
                    timestamp TEXT,
                    last_updated TEXT,
                    group_id TEXT,
                    FOREIGN KEY (group_id) REFERENCES groups(id)
                )
            ''')
            
            # Таблица учеников
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS students (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    status TEXT,
                    balance INTEGER,
                    site_url TEXT,
                    crm_type TEXT,
                    last_updated TEXT
                )
            ''')
            
            # Таблица групп
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    site_url TEXT,
                    crm_type TEXT,
                    last_updated TEXT
                )
            ''')
            
            # Связь уроков и учеников
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lesson_students (
                    lesson_id TEXT,
                    student_id TEXT,
                    status_on_lesson TEXT,
                    is_cancelled INTEGER DEFAULT 0,
                    is_paused INTEGER DEFAULT 0,
                    is_absent INTEGER DEFAULT 0,
                    is_rescheduled INTEGER DEFAULT 0,
                    is_completed INTEGER DEFAULT 0,
                    pause_info TEXT,
                    extra_info TEXT,
                    PRIMARY KEY (lesson_id, student_id)
                )
            ''')
            
            # Связь уроков и групп
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lesson_groups (
                    lesson_id TEXT,
                    group_id TEXT,
                    PRIMARY KEY (lesson_id, group_id)
                )
            ''')
            
            # Остальные таблицы (существующие)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    value TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cookies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    value TEXT,
                    domain TEXT,
                    path TEXT,
                    expires TEXT,
                    is_http_only INTEGER,
                    is_secure INTEGER,
                    profile TEXT,
                    created_at TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson_id TEXT,
                    message TEXT,
                    timestamp TEXT,
                    is_read INTEGER DEFAULT 0
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lesson_balances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT,
                    customer_name TEXT,
                    balance INTEGER,
                    crm_type TEXT,
                    site_url TEXT,
                    last_updated TEXT,
                    UNIQUE(customer_id, crm_type)
                )
            ''')
            
            # Добавляем новые колонки если их нет
            try:
                cursor.execute('ALTER TABLE lessons ADD COLUMN topic TEXT')
            except sqlite3.OperationalError:
                pass
                
            try:
                cursor.execute('ALTER TABLE lessons ADD COLUMN group_id TEXT')
            except sqlite3.OperationalError:
                pass
                
            try:
                cursor.execute('ALTER TABLE lessons DROP COLUMN group_name')
            except sqlite3.OperationalError:
                pass
                
            try:
                cursor.execute('ALTER TABLE lessons ADD COLUMN balance INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass
            
            # Добавляем поле для темы в таблицу lesson_students
            try:
                cursor.execute('ALTER TABLE lesson_students ADD COLUMN is_trial INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass
    
    # ==================== МЕТОДЫ ДЛЯ УЧЕНИКОВ ====================
    def save_student(self, student_id, name, status=None, balance=None, site_url=None, crm_type=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO students 
                (id, name, status, balance, site_url, crm_type, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (student_id, name, status, balance, site_url, crm_type, datetime.now().isoformat()))
    
    def get_student(self, student_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_students(self, crm_type=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if crm_type:
                cursor.execute('SELECT * FROM students WHERE crm_type = ? ORDER BY name', (crm_type,))
            else:
                cursor.execute('SELECT * FROM students ORDER BY name')
            return [dict(row) for row in cursor.fetchall()]
    
    def update_student_balance(self, student_id, balance):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE students SET balance = ?, last_updated = ?
                WHERE id = ?
            ''', (balance, datetime.now().isoformat(), student_id))
    
    # ==================== МЕТОДЫ ДЛЯ ГРУПП ====================
    def save_group(self, group_id, name, site_url=None, crm_type=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO groups 
                (id, name, site_url, crm_type, last_updated)
                VALUES (?, ?, ?, ?, ?)
            ''', (group_id, name, site_url, crm_type, datetime.now().isoformat()))
    
    def get_group(self, group_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM groups WHERE id = ?', (group_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_groups(self, crm_type=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if crm_type:
                cursor.execute('SELECT * FROM groups WHERE crm_type = ? ORDER BY name', (crm_type,))
            else:
                cursor.execute('SELECT * FROM groups ORDER BY name')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_group_by_name(self, name, crm_type=None):
        """Получает группу по названию"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if crm_type:
                cursor.execute('SELECT * FROM groups WHERE name = ? AND crm_type = ?', (name, crm_type))
            else:
                cursor.execute('SELECT * FROM groups WHERE name = ?', (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ==================== МЕТОДЫ ДЛЯ СВЯЗЕЙ ====================
    def save_lesson_student(self, lesson_id, student_id, status_on_lesson=None, 
                           is_cancelled=False, is_paused=False, is_absent=False,
                           is_rescheduled=False, is_completed=False,
                           pause_info=None, extra_info=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO lesson_students 
                (lesson_id, student_id, status_on_lesson, is_cancelled, is_paused, 
                 is_absent, is_rescheduled, is_completed, pause_info, extra_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (lesson_id, student_id, status_on_lesson, 
                  1 if is_cancelled else 0,
                  1 if is_paused else 0,
                  1 if is_absent else 0,
                  1 if is_rescheduled else 0,
                  1 if is_completed else 0,
                  pause_info, extra_info))
    
    def save_lesson_group(self, lesson_id, group_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO lesson_groups (lesson_id, group_id)
                VALUES (?, ?)
            ''', (lesson_id, group_id))
    
    def get_lesson_students(self, lesson_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    s.id as student_id,
                    s.name,
                    s.status,
                    s.balance,
                    s.site_url,
                    s.crm_type,
                    s.last_updated,
                    ls.lesson_id,
                    ls.status_on_lesson,
                    ls.is_cancelled,
                    ls.is_paused,
                    ls.is_absent,
                    ls.is_rescheduled,
                    ls.is_completed,
                    ls.pause_info,
                    ls.extra_info
                FROM lesson_students ls
                JOIN students s ON ls.student_id = s.id
                WHERE ls.lesson_id = ?
            ''', (lesson_id,))
            rows = cursor.fetchall()
            result = []
            for row in rows:
                data = dict(row)
                # Переименовываем student_id обратно в id для совместимости
                data['id'] = data.pop('student_id')
                result.append(data)
            return result
    
    def get_lesson_groups(self, lesson_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT g.* 
                FROM lesson_groups lg
                JOIN groups g ON lg.group_id = g.id
                WHERE lg.lesson_id = ?
            ''', (lesson_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_student_lessons(self, student_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT l.*, ls.status_on_lesson, ls.is_cancelled, ls.is_paused, 
                       ls.is_absent, ls.is_rescheduled, ls.is_completed
                FROM lesson_students ls
                JOIN lessons l ON ls.lesson_id = l.id
                WHERE ls.student_id = ?
                ORDER BY l.date DESC, l.time DESC
            ''', (student_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_group_lessons(self, group_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT l.*
                FROM lesson_groups lg
                JOIN lessons l ON lg.lesson_id = l.id
                WHERE lg.group_id = ?
                ORDER BY l.date DESC, l.time DESC
            ''', (group_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== СУЩЕСТВУЮЩИЕ МЕТОДЫ (С ОБНОВЛЕНИЯМИ) ====================
    def save_lessons(self, lessons):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            for lesson in lessons:
                cursor.execute('''
                    INSERT OR REPLACE INTO lessons 
                    (id, date, time, client, subject, topic, comment, status, link, 
                    teacher, room, type, is_occupied, customer_id, crm_type, 
                    site_url, timestamp, last_updated, group_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lesson.get('id', ''),
                    lesson.get('date', ''),
                    lesson.get('time', ''),
                    lesson.get('client', ''),
                    lesson.get('subject', ''),
                    lesson.get('topic', ''),
                    lesson.get('comment', ''),
                    lesson.get('status', ''),
                    lesson.get('link', ''),
                    lesson.get('teacher', ''),
                    lesson.get('room', ''),
                    lesson.get('type', ''),
                    1 if lesson.get('is_occupied', False) else 0,
                    lesson.get('customer_id', ''),
                    lesson.get('crm_type', ''),
                    lesson.get('site_url', ''),
                    lesson.get('timestamp', now),
                    now,
                    lesson.get('group_id', '')
                ))
    
    def get_lessons_for_date(self, date):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM lessons WHERE date = ? ORDER BY time', (date,))
            return [dict(row) for row in cursor.fetchall()]
            
    def get_lessons_for_period(self, start_date, end_date):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM lessons WHERE date BETWEEN ? AND ? ORDER BY date, time', (start_date, end_date))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Ошибка получения уроков get_lessons_for_period: {e}")
            return []

    def get_changed_lessons(self, new_lessons):
        changed = []
        for new_lesson in new_lessons:
            old = self.get_lesson(new_lesson.get('id'))
            if not old:
                changed.append({'type': 'new', 'lesson': new_lesson})
            else:
                changes = {}
                for key in ['time', 'client', 'subject', 'comment', 'status', 'teacher', 'room']:
                    if old.get(key) != new_lesson.get(key):
                        changes[key] = {'old': old.get(key), 'new': new_lesson.get(key)}
                if changes:
                    changed.append({'type': 'updated', 'lesson': new_lesson, 'changes': changes})
        return changed
        
    def get_lesson(self, lesson_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM lessons WHERE id = ?', (lesson_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_lesson_with_details(self, lesson_id):
        """Получает урок со всеми связями (ученики и группы)"""
        lesson = self.get_lesson(lesson_id)
        if not lesson:
            return None
        
        # Получаем учеников
        lesson['students'] = self.get_lesson_students(lesson_id)
        
        # Получаем группы
        lesson['groups'] = self.get_lesson_groups(lesson_id)
        
        return lesson
            
    def save_notification(self, notification):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO notifications (lesson_id, message, timestamp) VALUES (?, ?, ?)',
                           (notification.get('lesson_id', ''), notification.get('message', ''), datetime.now().isoformat()))
            
    def get_notifications(self, limit=50):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM notifications ORDER BY timestamp DESC LIMIT ?', (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Ошибка получения уведомлений get_notifications: {e}")
            return []
            
    def mark_notification_read(self, notification_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (notification_id,))
            
    def get_setting(self, key, default=None):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
                row = cursor.fetchone()
                return row['value'] if row else default
        except Exception as e:
            print(f"Ошибка получения настройки get_setting: {e}")
            return default
            
    def set_setting(self, key, value):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    
    # ==================== МЕТОДЫ ДЛЯ ОСТАТКОВ ====================
    def save_lesson_balance(self, customer_id, customer_name, balance, crm_type, site_url):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO lesson_balances 
                (customer_id, customer_name, balance, crm_type, site_url, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (customer_id, customer_name, balance, crm_type, site_url, datetime.now().isoformat()))
            conn.commit()
            
            # Также обновляем в таблице students
            self.update_student_balance(customer_id, balance)

    def get_lesson_balance(self, customer_id, crm_type):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM lesson_balances 
                WHERE customer_id = ? AND crm_type = ?
            ''', (customer_id, crm_type))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_lesson_balances(self, crm_type=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if crm_type:
                cursor.execute('SELECT * FROM lesson_balances WHERE crm_type = ?', (crm_type,))
            else:
                cursor.execute('SELECT * FROM lesson_balances')
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== МЕТОДЫ ДЛЯ COOKIES ====================
    def save_session_cookies(self, cookies, profile='rts'):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM cookies WHERE profile = ?', (profile,))
            for cookie in cookies:
                expiry = cookie.get('expiry')
                if expiry:
                    try:
                        expiry = int(expiry)
                    except:
                        expiry = None
                cursor.execute('''
                    INSERT INTO cookies (name, value, domain, path, expires, is_http_only, is_secure, profile, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    cookie.get('name', ''),
                    cookie.get('value', ''),
                    cookie.get('domain', ''),
                    cookie.get('path', '/'),
                    expiry,
                    1 if cookie.get('httpOnly', False) else 0,
                    1 if cookie.get('secure', False) else 0,
                    profile,
                    datetime.now().isoformat()
                ))
            conn.commit()

    def get_session_cookies(self, profile='rts'):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM cookies WHERE profile = ?', (profile,))
            cookies = []
            for row in cursor.fetchall():
                cookie = {
                    'name': row['name'],
                    'value': row['value'],
                    'domain': row['domain'],
                    'path': row['path'],
                    'httpOnly': bool(row['is_http_only']),
                    'secure': bool(row['is_secure'])
                }
                if row['expires']:
                    cookie['expiry'] = int(row['expires'])
                cookies.append(cookie)
            return cookies
    def get_all_groups_with_lessons(self, crm_type=None):
        """Получает все группы с количеством уроков"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if crm_type:
                cursor.execute('''
                    SELECT g.*, COUNT(lg.lesson_id) as lesson_count
                    FROM groups g
                    LEFT JOIN lesson_groups lg ON g.id = lg.group_id
                    WHERE g.crm_type = ?
                    GROUP BY g.id
                    ORDER BY g.name
                ''', (crm_type,))
            else:
                cursor.execute('''
                    SELECT g.*, COUNT(lg.lesson_id) as lesson_count
                    FROM groups g
                    LEFT JOIN lesson_groups lg ON g.id = lg.group_id
                    GROUP BY g.id
                    ORDER BY g.name
                ''')
            return [dict(row) for row in cursor.fetchall()]
    def update_groups_cache(self):
        """Обновляет кеш групп в БД"""
        if not self.is_logged_in:
            if not self.login():
                return False
        
        try:
            print("Обновление кеша групп...")
            groups = self.get_teacher_groups()
            
            if groups:
                print(f"Обновлено {len(groups)} групп в кеше")
                return True
            else:
                print("Не удалось получить группы")
                return False
                
        except Exception as e:
            print(f"Ошибка обновления кеша групп: {e}")
            return False