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
                    last_updated TEXT
                )
            ''')
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
    
    def save_session_cookies(self, cookies):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM cookies')
            for cookie in cookies:
                expiry = cookie.get('expiry')
                if expiry:
                    try:
                        expiry = int(expiry)
                    except:
                        expiry = None
                cursor.execute('''
                    INSERT INTO cookies (name, value, domain, path, expires, is_http_only, is_secure, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    cookie.get('name', ''),
                    cookie.get('value', ''),
                    cookie.get('domain', ''),
                    cookie.get('path', '/'),
                    expiry,
                    1 if cookie.get('httpOnly', False) else 0,
                    1 if cookie.get('secure', False) else 0,
                    datetime.now().isoformat()
                ))
            conn.commit()

    def get_session_cookies(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM cookies')
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
    
    def save_lessons(self, lessons):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            for lesson in lessons:
                cursor.execute('''
                    INSERT OR REPLACE INTO lessons 
                    (id, date, time, client, subject, comment, status, link, teacher, room, type, is_occupied, customer_id, crm_type, site_url, timestamp, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lesson.get('id', ''),
                    lesson.get('date', ''),
                    lesson.get('time', ''),
                    lesson.get('client', ''),
                    lesson.get('subject', ''),
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
                    now
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