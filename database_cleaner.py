# -*- coding: utf-8 -*-
"""
database_cleaner.py - Утилита для очистки базы данных
Удаляет таблицы, кроме cookies (сессии)
"""

import sqlite3
import os
from datetime import datetime


class DatabaseCleaner:
    def __init__(self, db_path='alfacrm_data.db'):
        self.db_path = db_path
        
    def get_connection(self):
        """Получает соединение с БД"""
        return sqlite3.connect(self.db_path)
    
    def get_all_tables(self):
        """Получает список всех таблиц в БД"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            return tables
    
    def drop_all_tables_except_cookies(self):
        """
        Удаляет ВСЕ таблицы, КРОМЕ cookies.
        Это полное удаление таблиц с последующим пересозданием.
        """
        tables_to_keep = ['cookies', 'sqlite_sequence']
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Отключаем внешние ключи для безопасного удаления
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            tables = self.get_all_tables()
            dropped_count = 0
            
            for table in tables:
                if table not in tables_to_keep:
                    try:
                        cursor.execute(f"DROP TABLE IF EXISTS {table}")
                        dropped_count += 1
                        print(f"✅ Удалена таблица: {table}")
                    except Exception as e:
                        print(f"❌ Ошибка удаления таблицы {table}: {e}")
            
            # Включаем внешние ключи обратно
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            
            print(f"\n📊 Удалено {dropped_count} таблиц")
            return dropped_count
    
    def reset_database(self):
        """
        Полный сброс БД: удаляет все таблицы кроме cookies и пересоздает структуру
        """
        print("🔄 Начинаем полный сброс базы данных...")
        print("=" * 60)
        
        # 1. Удаляем таблицы кроме cookies
        self.drop_all_tables_except_cookies()
        
        # 2. Пересоздаем структуру БД
        print("\n📝 Пересоздаем структуру базы данных...")
        try:
            from database import Database
            db = Database(self.db_path)
            print("✅ Структура базы данных пересоздана!")
        except ImportError as e:
            print(f"❌ Ошибка импорта Database: {e}")
            print("   Попробуйте создать структуру вручную через database.py")
            return False
        
        print("\n" + "=" * 60)
        print("✅ База данных полностью пересоздана!")
        print("   (Сессии (cookies) сохранены)")
        print("=" * 60)
        
        return True
    
    def drop_lessons_tables(self):
        """Удаляет таблицы уроков и связанные с ними"""
        tables_to_drop = ['lessons', 'lesson_students', 'lesson_groups']
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            for table in tables_to_drop:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
                    print(f"✅ Удалена таблица: {table}")
                except Exception as e:
                    print(f"❌ Ошибка удаления таблицы {table}: {e}")
            
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            
            print("✅ Все таблицы уроков удалены")
            return True
    
    def drop_students_tables(self):
        """Удаляет таблицы учеников и связанные с ними"""
        tables_to_drop = ['students', 'lesson_students', 'lesson_balances']
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            for table in tables_to_drop:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
                    print(f"✅ Удалена таблица: {table}")
                except Exception as e:
                    print(f"❌ Ошибка удаления таблицы {table}: {e}")
            
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            
            print("✅ Все таблицы учеников удалены")
            return True
    
    def drop_groups_tables(self):
        """Удаляет таблицы групп и связанные с ними"""
        tables_to_drop = ['groups', 'lesson_groups']
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            for table in tables_to_drop:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
                    print(f"✅ Удалена таблица: {table}")
                except Exception as e:
                    print(f"❌ Ошибка удаления таблицы {table}: {e}")
            
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            
            print("✅ Все таблицы групп удалены")
            return True
    
    def drop_notifications_table(self):
        """Удаляет таблицу уведомлений"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DROP TABLE IF EXISTS notifications")
                conn.commit()
                print("✅ Таблица notifications удалена")
                return True
            except Exception as e:
                print(f"❌ Ошибка удаления таблицы notifications: {e}")
                return False
    
    def drop_settings_table(self):
        """Удаляет таблицу настроек"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DROP TABLE IF EXISTS settings")
                conn.commit()
                print("✅ Таблица settings удалена")
                return True
            except Exception as e:
                print(f"❌ Ошибка удаления таблицы settings: {e}")
                return False
    
    def drop_session_tables(self):
        """Удаляет таблицы сессий"""
        tables_to_drop = ['sessions']
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for table in tables_to_drop:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
                    print(f"✅ Удалена таблица: {table}")
                except Exception as e:
                    print(f"❌ Ошибка удаления таблицы {table}: {e}")
            conn.commit()
            return True
    
    def get_table_info(self):
        """Показывает информацию о всех таблицах"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            tables = self.get_all_tables()
            print("\n📊 Информация о таблицах:")
            print("-" * 60)
            
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    print(f"  {table}: {count} записей")
                except:
                    print(f"  {table}: (ошибка подсчета)")
            
            print("-" * 60)
            return tables


def main():
    """Основная функция для запуска из командной строки"""
    import sys
    
    print("=" * 60)
    print("🧹 Утилита удаления таблиц базы данных AlfaCRM")
    print("=" * 60)
    
    # Параметры
    db_path = 'alfacrm_data.db'
    
    # Проверяем существует ли БД
    if not os.path.exists(db_path):
        print(f"❌ База данных {db_path} не найдена!")
        return
    
    cleaner = DatabaseCleaner(db_path)
    
    # Показываем информацию о таблицах
    cleaner.get_table_info()
    
    print("\n" + "=" * 60)
    print("Доступные действия (УДАЛЕНИЕ таблиц):")
    print("=" * 60)
    print("  1. Полное удаление (все таблицы, кроме cookies) + пересоздание")
    print("  2. Удалить только таблицы уроков (lessons, lesson_students, lesson_groups)")
    print("  3. Удалить только таблицы учеников (students, lesson_students, lesson_balances)")
    print("  4. Удалить только таблицы групп (groups, lesson_groups)")
    print("  5. Удалить только таблицу уведомлений (notifications)")
    print("  6. Удалить только таблицу настроек (settings)")
    print("  7. Удалить ВСЕ таблицы (включая cookies) - ОСТОРОЖНО!")
    print("  0. Выход")
    print("=" * 60)
    
    choice = input("\nВыберите действие (0-7): ").strip()
    
    if choice == '1':
        confirm = input("⚠️  Вы уверены, что хотите УДАЛИТЬ все таблицы (кроме cookies) и ПЕРЕСОЗДАТЬ их? (y/N): ")
        if confirm.lower() == 'y':
            cleaner.reset_database()
    elif choice == '2':
        confirm = input("⚠️  Вы уверены, что хотите УДАЛИТЬ таблицы уроков? (y/N): ")
        if confirm.lower() == 'y':
            cleaner.drop_lessons_tables()
    elif choice == '3':
        confirm = input("⚠️  Вы уверены, что хотите УДАЛИТЬ таблицы учеников? (y/N): ")
        if confirm.lower() == 'y':
            cleaner.drop_students_tables()
    elif choice == '4':
        confirm = input("⚠️  Вы уверены, что хотите УДАЛИТЬ таблицы групп? (y/N): ")
        if confirm.lower() == 'y':
            cleaner.drop_groups_tables()
    elif choice == '5':
        cleaner.drop_notifications_table()
    elif choice == '6':
        cleaner.drop_settings_table()
    elif choice == '7':
        confirm = input("🚨 ВЫ УВЕРЕНЫ? Это удалит ВСЕ таблицы, включая cookies! (y/N): ")
        if confirm.lower() == 'y':
            confirm2 = input("🚨 ЕЩЕ РАЗ: Удалить ВСЕ таблицы? (ДА/нет): ")
            if confirm2.lower() == 'да':
                with cleaner.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA foreign_keys = OFF")
                    tables = cleaner.get_all_tables()
                    for table in tables:
                        try:
                            cursor.execute(f"DROP TABLE IF EXISTS {table}")
                            print(f"✅ Удалена таблица: {table}")
                        except Exception as e:
                            print(f"❌ Ошибка удаления таблицы {table}: {e}")
                    cursor.execute("PRAGMA foreign_keys = ON")
                    conn.commit()
                print("✅ Все таблицы удалены!")
    elif choice == '0':
        print("Выход...")
    else:
        print("❌ Неверный выбор!")
    
    # Показываем обновленную информацию о таблицах
    if choice != '0':
        print("\n📊 Состояние базы данных после операции:")
        cleaner.get_table_info()
    
    print("\n✅ Готово!")


if __name__ == '__main__':
    main()