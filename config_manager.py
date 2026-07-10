import json
import os
from datetime import datetime

class ConfigManager:
    def __init__(self, config_file='config.json', db=None):
        self.config_file = config_file
        self.db = db
        self.config = self.load_config()
        
    def load_config(self):
        """Загрузка конфигурации"""
        default_config = {
            'site_url': 'https://rtschool.s20.online',
            'username': '',
            'password': '',
            'check_interval_hours': 1,
            'chromedriver_path': '',
            'theme': 'dark',
            'notifications_enabled': True,
            'auto_start': False
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Обновляем дефолтные значения
                    for key in default_config:
                        if key not in config:
                            config[key] = default_config[key]
                    return config
            except Exception as e:
                print(f"Ошибка загрузки конфига: {e}")
                return default_config
        else:
            self.save_config(default_config)
            return default_config
            
    def save_config(self, config=None):
        """Сохранение конфигурации"""
        if config is None:
            config = self.config
            
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Ошибка сохранения конфига: {e}")
            return False
            
    def get(self, key, default=None):
        """Получение значения настройки"""
        # Сначала проверяем в БД
        if self.db:
            value = self.db.get_setting(key)
            if value is not None:
                return value
        return self.config.get(key, default)
        
    def set(self, key, value):
        """Установка значения настройки"""
        self.config[key] = value
        
        # Сохраняем в БД
        if self.db:
            self.db.set_setting(key, str(value))
            
        self.save_config()