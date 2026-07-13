# -*- coding: utf-8 -*-
import sqlite3
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
import asyncio
import aiosqlite
from typing import List, Dict, Any, Optional


class Database:
    """Асинхронная версия Database с поддержкой FOREIGN KEY"""
    
    def __init__(self, db_path='alfacrm_data.db'):
        self.db_path = db_path
        self._pool = None
        self._init_sync()
        
    def _init_sync(self):
        """Синхронная инициализация БД (для первого запуска)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Включаем FOREIGN KEY поддержку
            cursor.execute("PRAGMA foreign_keys = ON")
            
            # ========== ТАБЛИЦА ГРУПП ==========
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    site_url TEXT,
                    crm_type TEXT,
                    last_updated TEXT
                )
            ''')
            
            # ========== ТАБЛИЦА УЧЕНИКОВ ==========
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS students (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    balance INTEGER DEFAULT 0,
                    site_url TEXT,
                    crm_type TEXT,
                    last_updated TEXT
                )
            ''')
            
            # ========== ТАБЛИЦА УРОКОВ ==========
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY,
                    date TEXT,
                    time TEXT,
                    client TEXT,
                    subject TEXT,
                    topic TEXT,
                    comment TEXT,
                    status TEXT,
                    link TEXT,
                    teacher TEXT,
                    room TEXT,
                    type TEXT,
                    is_occupied INTEGER DEFAULT 0,
                    customer_id TEXT,
                    crm_type TEXT,
                    site_url TEXT,
                    timestamp TEXT,
                    last_updated TEXT,
                    group_id TEXT,
                    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL,
                    FOREIGN KEY (customer_id) REFERENCES students(id) ON DELETE SET NULL
                )
            ''')
            
            # ========== СВЯЗЬ УРОКОВ И УЧЕНИКОВ ==========
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lesson_students (
                    lesson_id TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    status_on_lesson TEXT,
                    is_cancelled INTEGER DEFAULT 0,
                    is_paused INTEGER DEFAULT 0,
                    is_absent INTEGER DEFAULT 0,
                    is_rescheduled INTEGER DEFAULT 0,
                    is_completed INTEGER DEFAULT 0,
                    pause_info TEXT,
                    extra_info TEXT,
                    PRIMARY KEY (lesson_id, student_id),
                    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
                    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
                )
            ''')
            
            # ========== СВЯЗЬ УРОКОВ И ГРУПП ==========
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lesson_groups (
                    lesson_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    PRIMARY KEY (lesson_id, group_id),
                    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
                    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
                )
            ''')
            
            # ========== ОСТАТКИ УРОКОВ ==========
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lesson_balances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    customer_name TEXT,
                    balance INTEGER DEFAULT 0,
                    crm_type TEXT,
                    site_url TEXT,
                    last_updated TEXT,
                    UNIQUE(customer_id, crm_type),
                    FOREIGN KEY (customer_id) REFERENCES students(id) ON DELETE CASCADE
                )
            ''')
            
            # ========== COOKIES ==========
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cookies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    value TEXT,
                    domain TEXT,
                    path TEXT,
                    expires TEXT,
                    is_http_only INTEGER DEFAULT 0,
                    is_secure INTEGER DEFAULT 0,
                    profile TEXT,
                    created_at TEXT
                )
            ''')
            
            # ========== УВЕДОМЛЕНИЯ ==========
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson_id TEXT,
                    message TEXT,
                    timestamp TEXT,
                    is_read INTEGER DEFAULT 0,
                    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
                )
            ''')
            
            # ========== НАСТРОЙКИ ==========
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # ========== ИНДЕКСЫ ==========
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_lessons_date ON lessons(date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_lessons_group_id ON lessons(group_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_lessons_customer_id ON lessons(customer_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_lesson_students_lesson ON lesson_students(lesson_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_lesson_students_student ON lesson_students(student_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_lesson_groups_lesson ON lesson_groups(lesson_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_lesson_groups_group ON lesson_groups(group_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_groups_name ON groups(name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_students_name ON students(name)')
            
            conn.commit()
    
    async def get_connection(self):
        """Получает асинхронное соединение с БД"""
        conn = await aiosqlite.connect(self.db_path)
        await conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = aiosqlite.Row
        return conn
    
    # ==================== УРОКИ ====================
    
    async def save_lesson(self, lesson: Dict[str, Any]):
        """Сохраняет один урок с проверкой внешних ключей"""
        conn = await self.get_connection()
        try:
            # Проверяем и сохраняем группу если есть
            group_id = lesson.get('group_id')
            if group_id:
                # Проверяем существует ли группа
                cursor = await conn.execute('SELECT id FROM groups WHERE id = ?', (group_id,))
                existing = await cursor.fetchone()
                if not existing:
                    # Если группы нет - создаем
                    group_name = f"Группа #{group_id}"
                    await conn.execute('''
                        INSERT OR IGNORE INTO groups (id, name, site_url, crm_type, last_updated)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (group_id, group_name, lesson.get('site_url'), lesson.get('crm_type'), datetime.now().isoformat()))
                    await conn.commit()
                    print(f"Создана группа {group_id} для урока {lesson.get('id')}")
            
            # Проверяем и сохраняем ученика если есть
            customer_id = lesson.get('customer_id')
            if customer_id:
                cursor = await conn.execute('SELECT id FROM students WHERE id = ?', (customer_id,))
                existing = await cursor.fetchone()
                if not existing:
                    # Если ученика нет - создаем временную запись
                    await conn.execute('''
                        INSERT OR IGNORE INTO students (id, name, status, crm_type, last_updated)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (customer_id, lesson.get('client', 'Неизвестно'), 'active', lesson.get('crm_type'), datetime.now().isoformat()))
                    await conn.commit()
                    print(f"Создан ученик {customer_id} для урока {lesson.get('id')}")
            
            # Теперь сохраняем урок
            now = datetime.now().isoformat()
            await conn.execute('''
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
            await conn.commit()
            
        except sqlite3.IntegrityError as e:
            print(f"Ошибка целостности при сохранении урока {lesson.get('id')}: {e}")
            # Пробуем сохранить без group_id
            try:
                # Убираем group_id и пробуем снова
                lesson_copy = lesson.copy()
                lesson_copy['group_id'] = None
                await conn.execute('''
                    INSERT OR REPLACE INTO lessons 
                    (id, date, time, client, subject, topic, comment, status, link, 
                    teacher, room, type, is_occupied, customer_id, crm_type, 
                    site_url, timestamp, last_updated, group_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lesson_copy.get('id', ''),
                    lesson_copy.get('date', ''),
                    lesson_copy.get('time', ''),
                    lesson_copy.get('client', ''),
                    lesson_copy.get('subject', ''),
                    lesson_copy.get('topic', ''),
                    lesson_copy.get('comment', ''),
                    lesson_copy.get('status', ''),
                    lesson_copy.get('link', ''),
                    lesson_copy.get('teacher', ''),
                    lesson_copy.get('room', ''),
                    lesson_copy.get('type', ''),
                    1 if lesson_copy.get('is_occupied', False) else 0,
                    lesson_copy.get('customer_id', ''),
                    lesson_copy.get('crm_type', ''),
                    lesson_copy.get('site_url', ''),
                    lesson_copy.get('timestamp', now),
                    now,
                    None
                ))
                await conn.commit()
                print(f"Урок {lesson.get('id')} сохранен без group_id")
            except Exception as e2:
                print(f"Не удалось сохранить урок {lesson.get('id')}: {e2}")
                raise
        finally:
            await conn.close()
    
    async def save_lessons(self, lessons: List[Dict[str, Any]]):
        """Сохраняет несколько уроков"""
        for lesson in lessons:
            try:
                await self.save_lesson(lesson)
            except Exception as e:
                print(f"Ошибка сохранения урока {lesson.get('id')}: {e}")
                # Продолжаем со следующим уроком
                continue
    
    async def get_lesson(self, lesson_id: str) -> Optional[Dict[str, Any]]:
        """Получает урок по ID"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('SELECT * FROM lessons WHERE id = ?', (lesson_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await conn.close()
    
    async def get_lessons_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Получает уроки за дату"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute(
                'SELECT * FROM lessons WHERE date = ? ORDER BY time', 
                (date,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    
    async def get_lessons_for_period(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Получает уроки за период"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute(
                'SELECT * FROM lessons WHERE date BETWEEN ? AND ? ORDER BY date, time',
                (start_date, end_date)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    
    async def get_lessons_by_group(self, group_id: str) -> List[Dict[str, Any]]:
        """Получает уроки группы"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('''
                SELECT l.* FROM lessons l
                JOIN lesson_groups lg ON l.id = lg.lesson_id
                WHERE lg.group_id = ?
                ORDER BY l.date, l.time
            ''', (group_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    
    async def get_changed_lessons(self, new_lessons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Находит изменения в уроках"""
        changed = []
        for new_lesson in new_lessons:
            old = await self.get_lesson(new_lesson.get('id'))
            if not old:
                changed.append({'type': 'new', 'lesson': new_lesson})
            else:
                changes = {}
                for key in ['time', 'client', 'subject', 'topic', 'comment', 'status', 'teacher', 'room']:
                    if old.get(key) != new_lesson.get(key):
                        changes[key] = {'old': old.get(key), 'new': new_lesson.get(key)}
                if changes:
                    changed.append({'type': 'updated', 'lesson': new_lesson, 'changes': changes})
        return changed
    
    # ==================== УЧЕНИКИ ====================
    
    async def save_student(self, student_id: str, name: str, status: str = 'active', 
                           balance: int = 0, site_url: str = None, crm_type: str = None):
        """Сохраняет ученика"""
        conn = await self.get_connection()
        try:
            await conn.execute('''
                INSERT OR REPLACE INTO students 
                (id, name, status, balance, site_url, crm_type, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (student_id, name, status, balance, site_url, crm_type, datetime.now().isoformat()))
            await conn.commit()
        finally:
            await conn.close()
    
    async def get_student(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Получает ученика по ID"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('SELECT * FROM students WHERE id = ?', (student_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await conn.close()
    
    async def get_all_students(self, crm_type: str = None) -> List[Dict[str, Any]]:
        """Получает всех учеников"""
        conn = await self.get_connection()
        try:
            if crm_type:
                cursor = await conn.execute(
                    'SELECT * FROM students WHERE crm_type = ? ORDER BY name', 
                    (crm_type,)
                )
            else:
                cursor = await conn.execute('SELECT * FROM students ORDER BY name')
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    
    async def update_student_balance(self, student_id: str, balance: int):
        """Обновляет баланс ученика"""
        conn = await self.get_connection()
        try:
            await conn.execute('''
                UPDATE students SET balance = ?, last_updated = ?
                WHERE id = ?
            ''', (balance, datetime.now().isoformat(), student_id))
            await conn.commit()
        finally:
            await conn.close()
    
    # ==================== ГРУППЫ ====================
    
    async def save_group(self, group_id: str, name: str, site_url: str = None, crm_type: str = None):
        """Сохраняет группу"""
        conn = await self.get_connection()
        try:
            await conn.execute('''
                INSERT OR REPLACE INTO groups 
                (id, name, site_url, crm_type, last_updated)
                VALUES (?, ?, ?, ?, ?)
            ''', (group_id, name, site_url, crm_type, datetime.now().isoformat()))
            await conn.commit()
        finally:
            await conn.close()
            
    async def ensure_group_exists(self, group_id: str, group_name: str = None, site_url: str = None, crm_type: str = None):
        """Проверяет существование группы и создает если нет"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('SELECT id FROM groups WHERE id = ?', (group_id,))
            existing = await cursor.fetchone()
            if not existing:
                if not group_name:
                    group_name = f"Группа #{group_id}"
                await conn.execute('''
                    INSERT OR IGNORE INTO groups (id, name, site_url, crm_type, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                ''', (group_id, group_name, site_url, crm_type, datetime.now().isoformat()))
                await conn.commit()
                print(f"Создана группа: {group_id} - {group_name}")
            return True
        finally:
            await conn.close()

    async def ensure_student_exists(self, student_id: str, student_name: str = None, crm_type: str = None):
        """Проверяет существование ученика и создает если нет"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('SELECT id FROM students WHERE id = ?', (student_id,))
            existing = await cursor.fetchone()
            if not existing:
                if not student_name:
                    student_name = f"Ученик #{student_id}"
                await conn.execute('''
                    INSERT OR IGNORE INTO students (id, name, status, crm_type, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                ''', (student_id, student_name, 'active', crm_type, datetime.now().isoformat()))
                await conn.commit()
                print(f"Создан ученик: {student_id} - {student_name}")
            return True
        finally:
            await conn.close()
    
    async def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Получает группу по ID"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('SELECT * FROM groups WHERE id = ?', (group_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await conn.close()
    
    async def get_group_by_name(self, name: str, crm_type: str = None) -> Optional[Dict[str, Any]]:
        """Получает группу по названию"""
        conn = await self.get_connection()
        try:
            if crm_type:
                cursor = await conn.execute(
                    'SELECT * FROM groups WHERE name = ? AND crm_type = ?', 
                    (name, crm_type)
                )
            else:
                cursor = await conn.execute('SELECT * FROM groups WHERE name = ?', (name,))
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await conn.close()
    
    async def get_all_groups(self, crm_type: str = None) -> List[Dict[str, Any]]:
        """Получает все группы"""
        conn = await self.get_connection()
        try:
            if crm_type:
                cursor = await conn.execute(
                    'SELECT * FROM groups WHERE crm_type = ? ORDER BY name', 
                    (crm_type,)
                )
            else:
                cursor = await conn.execute('SELECT * FROM groups ORDER BY name')
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    
    # ==================== СВЯЗИ ====================
    
    async def save_lesson_student(self, lesson_id: str, student_id: str, 
                                   status_on_lesson: str = None,
                                   is_cancelled: bool = False, is_paused: bool = False,
                                   is_absent: bool = False, is_rescheduled: bool = False,
                                   is_completed: bool = False,
                                   pause_info: str = None, extra_info: str = None):
        """Сохраняет связь урок-ученик"""
        conn = await self.get_connection()
        try:
            await conn.execute('''
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
            await conn.commit()
        finally:
            await conn.close()
    
    async def save_lesson_group(self, lesson_id: str, group_id: str):
        """Сохраняет связь урок-группа"""
        conn = await self.get_connection()
        try:
            await conn.execute('''
                INSERT OR REPLACE INTO lesson_groups (lesson_id, group_id)
                VALUES (?, ?)
            ''', (lesson_id, group_id))
            await conn.commit()
        finally:
            await conn.close()
    
    async def get_lesson_students(self, lesson_id: str) -> List[Dict[str, Any]]:
        """Получает учеников урока"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('''
                SELECT 
                    s.id,
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
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    
    async def get_lesson_groups(self, lesson_id: str) -> List[Dict[str, Any]]:
        """Получает группы урока"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('''
                SELECT g.* 
                FROM lesson_groups lg
                JOIN groups g ON lg.group_id = g.id
                WHERE lg.lesson_id = ?
            ''', (lesson_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    
    async def get_student_lessons(self, student_id: str) -> List[Dict[str, Any]]:
        """Получает уроки ученика"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('''
                SELECT l.*, ls.status_on_lesson, ls.is_cancelled, ls.is_paused, 
                       ls.is_absent, ls.is_rescheduled, ls.is_completed
                FROM lesson_students ls
                JOIN lessons l ON ls.lesson_id = l.id
                WHERE ls.student_id = ?
                ORDER BY l.date DESC, l.time DESC
            ''', (student_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    
    async def get_group_lessons(self, group_id: str) -> List[Dict[str, Any]]:
        """Получает уроки группы"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('''
                SELECT l.*
                FROM lesson_groups lg
                JOIN lessons l ON lg.lesson_id = l.id
                WHERE lg.group_id = ?
                ORDER BY l.date DESC, l.time DESC
            ''', (group_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    
    async def get_lesson_with_details(self, lesson_id: str) -> Optional[Dict[str, Any]]:
        """Получает урок со всеми связями"""
        lesson = await self.get_lesson(lesson_id)
        if not lesson:
            return None
        lesson['students'] = await self.get_lesson_students(lesson_id)
        lesson['groups'] = await self.get_lesson_groups(lesson_id)
        return lesson
    
    # ==================== ОСТАТКИ ====================
    
    async def save_lesson_balance(self, customer_id: str, customer_name: str, 
                                   balance: int, crm_type: str, site_url: str):
        """Сохраняет остаток уроков"""
        conn = await self.get_connection()
        try:
            await conn.execute('''
                INSERT OR REPLACE INTO lesson_balances 
                (customer_id, customer_name, balance, crm_type, site_url, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (customer_id, customer_name, balance, crm_type, site_url, datetime.now().isoformat()))
            await conn.commit()
            await self.update_student_balance(customer_id, balance)
        finally:
            await conn.close()
    
    async def get_lesson_balance(self, customer_id: str, crm_type: str) -> Optional[Dict[str, Any]]:
        """Получает остаток уроков"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('''
                SELECT * FROM lesson_balances 
                WHERE customer_id = ? AND crm_type = ?
            ''', (customer_id, crm_type))
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await conn.close()
    
    # ==================== УВЕДОМЛЕНИЯ ====================
    
    async def save_notification(self, notification: Dict[str, Any]):
        """Сохраняет уведомление"""
        conn = await self.get_connection()
        try:
            await conn.execute('''
                INSERT INTO notifications (lesson_id, message, timestamp)
                VALUES (?, ?, ?)
            ''', (notification.get('lesson_id', ''), 
                  notification.get('message', ''), 
                  datetime.now().isoformat()))
            await conn.commit()
        finally:
            await conn.close()
    
    async def get_notifications(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получает уведомления"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute(
                'SELECT * FROM notifications ORDER BY timestamp DESC LIMIT ?', 
                (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    
    # ==================== НАСТРОЙКИ ====================
    
    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Получает настройку"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('SELECT value FROM settings WHERE key = ?', (key,))
            row = await cursor.fetchone()
            return row['value'] if row else default
        finally:
            await conn.close()
    
    async def set_setting(self, key: str, value: str):
        """Устанавливает настройку"""
        conn = await self.get_connection()
        try:
            await conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
            await conn.commit()
        finally:
            await conn.close()
    
    # ==================== COOKIES ====================
    
    async def save_session_cookies(self, cookies: List[Dict], profile: str = 'rts'):
        """Сохраняет cookies"""
        conn = await self.get_connection()
        try:
            await conn.execute('DELETE FROM cookies WHERE profile = ?', (profile,))
            for cookie in cookies:
                expiry = cookie.get('expiry')
                if expiry:
                    try:
                        expiry = int(expiry)
                    except:
                        expiry = None
                await conn.execute('''
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
            await conn.commit()
        finally:
            await conn.close()
    
    async def get_session_cookies(self, profile: str = 'rts') -> List[Dict]:
        """Получает cookies"""
        conn = await self.get_connection()
        try:
            cursor = await conn.execute('SELECT * FROM cookies WHERE profile = ?', (profile,))
            rows = await cursor.fetchall()
            cookies = []
            for row in rows:
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
        finally:
            await conn.close()


# ==================== СИНХРОННАЯ ОБЕРТКА ДЛЯ СОВМЕСТИМОСТИ ====================

class SyncDatabase:
    """Синхронная обертка для обратной совместимости"""
    
    def __init__(self, db_path='alfacrm_data.db'):
        self.db_path = db_path
        self._async_db = Database(db_path)
        self._loop = None
    
    def _get_loop(self):
        """Получает или создает event loop"""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop
    
    def _run_async(self, coro):
        """Запускает асинхронную функцию синхронно"""
        try:
            loop = asyncio.get_running_loop()
            # Если цикл уже запущен, создаем новую задачу
            return asyncio.create_task(coro)
        except RuntimeError:
            # Нет запущенного цикла - создаем новый
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
    
    def save_lesson(self, lesson):
        return self._run_async(self._async_db.save_lesson(lesson))
    
    def save_lessons(self, lessons):
        return self._run_async(self._async_db.save_lessons(lessons))
    
    def get_lesson(self, lesson_id):
        return self._run_async(self._async_db.get_lesson(lesson_id))
    
    def get_lessons_for_date(self, date):
        return self._run_async(self._async_db.get_lessons_for_date(date))
    
    def get_lessons_for_period(self, start_date, end_date):
        return self._run_async(self._async_db.get_lessons_for_period(start_date, end_date))
    
    def get_lesson_students(self, lesson_id):
        return self._run_async(self._async_db.get_lesson_students(lesson_id))
    
    def get_lesson_groups(self, lesson_id):
        return self._run_async(self._async_db.get_lesson_groups(lesson_id))
    
    def get_group(self, group_id):
        return self._run_async(self._async_db.get_group(group_id))
    
    def get_group_by_name(self, name, crm_type=None):
        return self._run_async(self._async_db.get_group_by_name(name, crm_type))
    
    def save_group(self, group_id, name, site_url=None, crm_type=None):
        return self._run_async(self._async_db.save_group(group_id, name, site_url, crm_type))
    
    def save_student(self, student_id, name, status=None, balance=None, site_url=None, crm_type=None):
        return self._run_async(self._async_db.save_student(student_id, name, status, balance, site_url, crm_type))
    
    def save_lesson_student(self, lesson_id, student_id, status_on_lesson=None, 
                           is_cancelled=False, is_paused=False, is_absent=False,
                           is_rescheduled=False, is_completed=False,
                           pause_info=None, extra_info=None):
        return self._run_async(self._async_db.save_lesson_student(
            lesson_id, student_id, status_on_lesson, is_cancelled, is_paused,
            is_absent, is_rescheduled, is_completed, pause_info, extra_info
        ))
    
    def save_lesson_group(self, lesson_id, group_id):
        return self._run_async(self._async_db.save_lesson_group(lesson_id, group_id))
    
    def save_lesson_balance(self, customer_id, customer_name, balance, crm_type, site_url):
        return self._run_async(self._async_db.save_lesson_balance(customer_id, customer_name, balance, crm_type, site_url))
    
    def save_notification(self, notification):
        return self._run_async(self._async_db.save_notification(notification))
    
    def get_notifications(self, limit=50):
        return self._run_async(self._async_db.get_notifications(limit))
    
    def get_setting(self, key, default=None):
        return self._run_async(self._async_db.get_setting(key, default))
    
    def set_setting(self, key, value):
        return self._run_async(self._async_db.set_setting(key, value))
    
    def save_session_cookies(self, cookies, profile='rts'):
        return self._run_async(self._async_db.save_session_cookies(cookies, profile))
    
    def get_session_cookies(self, profile='rts'):
        return self._run_async(self._async_db.get_session_cookies(profile))
    
    def get_lesson_with_details(self, lesson_id):
        return self._run_async(self._async_db.get_lesson_with_details(lesson_id))
    
    def get_all_groups_with_lessons(self, crm_type=None):
        return self._run_async(self._async_db.get_all_groups(crm_type))
    
    # Добавить в класс Database (в асинхронную часть)

    async def delete_group(self, group_id: str):
        """Удаляет группу по ID"""
        conn = await self.get_connection()
        try:
            await conn.execute('DELETE FROM groups WHERE id = ?', (group_id,))
            await conn.commit()
            print(f"Удалена группа: {group_id}")
        finally:
            await conn.close()

    # Добавить в класс SyncDatabase (в синхронную обертку)

    def delete_group(self, group_id):
        return self._run_async(self._async_db.delete_group(group_id))