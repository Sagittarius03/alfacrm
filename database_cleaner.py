# -*- coding: utf-8 -*-
"""
clean_database.py - Утилита для очистки базы данных
Очищает все таблицы, кроме cookies (сессии)
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
    
    def clear_all_data(self):
        """Очищает все данные из всех таблиц, кроме cookies"""
        tables_to_keep = ['cookies']  # Таблицы, которые НЕ нужно очищать
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем все таблицы
            tables = self.get_all_tables()
            
            # Отключаем внешние ключи для безопасного удаления
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            deleted_count = 0
            for table in tables:
                if table not in tables_to_keep:
                    try:
                        cursor.execute(f"DELETE FROM {table}")
                        # Сбрасываем автоинкремент если есть
                        try:
                            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
                        except:
                            pass
                        deleted_count += 1
                        print(f"✅ Очищена таблица: {table}")
                    except Exception as e:
                        print(f"❌ Ошибка очистки таблицы {table}: {e}")
            
            # Включаем внешние ключи обратно
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            
            print(f"\n📊 Очищено {deleted_count} таблиц")
            return deleted_count
    
    def drop_all_tables(self):
        """Удаляет все таблицы, кроме cookies (полная пересоздание)"""
        tables_to_keep = ['cookies']  # Таблицы, которые НЕ нужно удалять
        
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
        """Полный сброс БД: удаляет все таблицы кроме cookies и пересоздает структуру"""
        print("🔄 Начинаем полный сброс базы данных...")
        
        # Удаляем таблицы кроме cookies
        self.drop_all_tables()
        
        # Импортируем Database для пересоздания структуры
        from database import Database
        
        # Пересоздаем структуру БД
        print("📝 Пересоздаем структуру базы данных...")
        db = Database(self.db_path)
        
        print("✅ База данных полностью пересоздана!")
        print("   (Сессии (cookies) сохранены)")
        
        return True
    
    def clear_lessons_only(self):
        """Очищает только уроки и связанные с ними данные"""
        tables_to_clear = ['lessons', 'lesson_students', 'lesson_groups']
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Отключаем внешние ключи
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            for table in tables_to_clear:
                try:
                    cursor.execute(f"DELETE FROM {table}")
                    print(f"✅ Очищена таблица: {table}")
                except Exception as e:
                    print(f"❌ Ошибка очистки таблицы {table}: {e}")
            
            # Включаем внешние ключи
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            
            print("✅ Все уроки и связи очищены")
            return True
    
    def clear_students_only(self):
        """Очищает только учеников и их связи"""
        tables_to_clear = ['students', 'lesson_students', 'lesson_balances']
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            for table in tables_to_clear:
                try:
                    cursor.execute(f"DELETE FROM {table}")
                    print(f"✅ Очищена таблица: {table}")
                except Exception as e:
                    print(f"❌ Ошибка очистки таблицы {table}: {e}")
            
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            
            print("✅ Все ученики и связи очищены")
            return True
    
    def clear_groups_only(self):
        """Очищает только группы и их связи"""
        tables_to_clear = ['groups', 'lesson_groups']
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            for table in tables_to_clear:
                try:
                    cursor.execute(f"DELETE FROM {table}")
                    print(f"✅ Очищена таблица: {table}")
                except Exception as e:
                    print(f"❌ Ошибка очистки таблицы {table}: {e}")
            
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            
            print("✅ Все группы и связи очищены")
            return True
    
    def clear_notifications_only(self):
        """Очищает только уведомления"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM notifications")
            conn.commit()
            print("✅ Все уведомления очищены")
            return True
    
    def get_table_info(self):
        """Показывает информацию о всех таблицах"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            tables = self.get_all_tables()
            print("\n📊 Информация о таблицах:")
            print("-" * 60)
            
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {table}: {count} записей")
            
            print("-" * 60)
            return tables


def main():
    """Основная функция для запуска из командной строки"""
    import sys
    
    print("=" * 60)
    print("🧹 Утилита очистки базы данных AlfaCRM")
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
    
    print("\nДоступные действия:")
    print("  1. Полная очистка (все таблицы, кроме cookies)")
    print("  2. Полный сброс (удалить и пересоздать все таблицы, кроме cookies)")
    print("  3. Очистить только уроки (lessons, lesson_students, lesson_groups)")
    print("  4. Очистить только учеников (students, lesson_students, lesson_balances)")
    print("  5. Очистить только группы (groups, lesson_groups)")
    print("  6. Очистить только уведомления (notifications)")
    print("  0. Выход")
    
    choice = input("\nВыберите действие (0-6): ").strip()
    
    if choice == '1':
        confirm = input("⚠️  Вы уверены, что хотите очистить ВСЕ таблицы (кроме cookies)? (y/N): ")
        if confirm.lower() == 'y':
            cleaner.clear_all_data()
    elif choice == '2':
        confirm = input("⚠️  Вы уверены, что хотите УДАЛИТЬ и ПЕРЕСОЗДАТЬ все таблицы (кроме cookies)? (y/N): ")
        if confirm.lower() == 'y':
            cleaner.reset_database()
    elif choice == '3':
        confirm = input("⚠️  Вы уверены, что хотите очистить все уроки и связи? (y/N): ")
        if confirm.lower() == 'y':
            cleaner.clear_lessons_only()
    elif choice == '4':
        confirm = input("⚠️  Вы уверены, что хотите очистить всех учеников и связи? (y/N): ")
        if confirm.lower() == 'y':
            cleaner.clear_students_only()
    elif choice == '5':
        confirm = input("⚠️  Вы уверены, что хотите очистить все группы и связи? (y/N): ")
        if confirm.lower() == 'y':
            cleaner.clear_groups_only()
    elif choice == '6':
        cleaner.clear_notifications_only()
    elif choice == '0':
        print("Выход...")
    else:
        print("❌ Неверный выбор!")
    
    print("\n✅ Готово!")


if __name__ == '__main__':
    main()