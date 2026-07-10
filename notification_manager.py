from plyer import notification
import json
from datetime import datetime
import threading

class NotificationManager:
    def __init__(self, db):
        self.db = db
        
    def send_notification(self, title, message, timeout=10):
        try:
            notification.notify(
                title=title[:64],
                message=message[:256],
                timeout=timeout,
                app_name="AlfaCRM Automation"
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления: {e}")
            
    def notify_lesson_changes(self, changes):
        if not changes:
            return
        for change in changes:
            lesson = change['lesson']
            change_type = change['type']
            if change_type == 'new':
                message = f"Новый урок: {lesson.get('client')} - {lesson.get('subject')} в {lesson.get('time')}"
                self.send_notification("Новый урок", message)
            elif change_type == 'updated':
                changes_text = []
                for key, value in change['changes'].items():
                    changes_text.append(f"{key}: {value['old']} -> {value['new']}")
                message = f"Изменения в уроке {lesson.get('client')}: {', '.join(changes_text)}"
                self.send_notification("Изменение урока", message)
            self.db.save_notification({
                'lesson_id': lesson.get('id', ''),
                'message': message
            })
            
    def notify_schedule_summary(self, lessons):
        free_slots = [l for l in lessons if not l.get('is_occupied', False)]
        occupied_slots = [l for l in lessons if l.get('is_occupied', False)]
        message = f"Расписание на сегодня:\nВсего уроков: {len(lessons)}\nЗанятых слотов: {len(occupied_slots)}\nСвободных слотов: {len(free_slots)}"
        self.send_notification("Сводка расписания", message)