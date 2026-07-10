from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import threading

class Scheduler:
    def __init__(self, alfacrm, db, notification_manager):
        self.alfacrm = alfacrm
        self.db = db
        self.notification_manager = notification_manager
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.check_interval_hours = 1
        
    def start(self):
        """Запуск планировщика"""
        if not self.is_running:
            # Задача проверки обновлений
            self.scheduler.add_job(
                self.check_updates,
                trigger=IntervalTrigger(hours=self.check_interval_hours),
                id='check_updates',
                replace_existing=True
            )
            
            # Утреннее уведомление о расписании
            self.scheduler.add_job(
                self.send_daily_schedule,
                trigger=CronTrigger(hour=8, minute=0),
                id='daily_schedule',
                replace_existing=True
            )
            
            self.scheduler.start()
            self.is_running = True
            print("Планировщик запущен")
            
    def stop(self):
        """Остановка планировщика"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            print("Планировщик остановлен")
            
    def check_updates(self):
        """Проверка обновлений"""
        print("Проверка обновлений...")
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            
            # Получаем уроки на сегодня и завтра
            lessons_today = self.alfacrm.get_lessons_schedule(today)
            lessons_tomorrow = self.alfacrm.get_lessons_schedule(tomorrow)
            
            all_lessons = lessons_today + lessons_tomorrow
            
            if all_lessons:
                # Сравниваем с сохраненными
                changed = self.db.get_changed_lessons(all_lessons)
                
                if changed:
                    self.notification_manager.notify_lesson_changes(changed)
                    
                # Сохраняем уроки
                self.db.save_lessons(all_lessons)
                
        except Exception as e:
            print(f"Ошибка при проверке обновлений: {e}")
            
    def send_daily_schedule(self):
        """Отправка ежедневного расписания"""
        print("Отправка ежедневного расписания...")
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            lessons = self.db.get_lessons_for_date(today)
            
            if lessons:
                self.notification_manager.notify_schedule_summary(lessons)
                
        except Exception as e:
            print(f"Ошибка отправки расписания: {e}")
            
    def set_check_interval(self, hours=1):
        """Установка интервала проверки"""
        self.check_interval_hours = hours
        
        # Если планировщик запущен, обновляем задачу
        if self.is_running:
            try:
                # Пытаемся найти и изменить задачу
                job = self.scheduler.get_job('check_updates')
                if job:
                    self.scheduler.reschedule_job(
                        'check_updates',
                        trigger=IntervalTrigger(hours=hours)
                    )
                    print(f"Интервал проверки обновлен на {hours} час(ов)")
                else:
                    # Если задачи нет, добавляем новую
                    self.scheduler.add_job(
                        self.check_updates,
                        trigger=IntervalTrigger(hours=hours),
                        id='check_updates',
                        replace_existing=True
                    )
                    print(f"Добавлена задача проверки с интервалом {hours} час(ов)")
            except Exception as e:
                print(f"Ошибка обновления интервала: {e}")
                # Если не удалось обновить, перезапускаем планировщик
                self.restart()
                
    def restart(self):
        """Перезапуск планировщика"""
        self.stop()
        self.start()