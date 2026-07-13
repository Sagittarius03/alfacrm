# -*- coding: utf-8 -*-
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


class AsyncTaskManager:
    """Менеджер асинхронных задач"""
    
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.tasks = []
    
    async def run_task(self, coro):
        """Запускает задачу с ограничением по количеству"""
        async with self.semaphore:
            return await coro
    
    def add_task(self, coro):
        """Добавляет задачу в список"""
        self.tasks.append(asyncio.create_task(coro))
    
    async def wait_all(self):
        """Ожидает завершения всех задач"""
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
            self.tasks = []
    
    def get_results(self):
        """Получает результаты всех задач"""
        results = []
        for task in self.tasks:
            if task.done() and not task.cancelled():
                try:
                    results.append(task.result())
                except Exception as e:
                    print(f"Ошибка в задаче: {e}")
        return results


class AsyncCache:
    """Простой асинхронный кеш"""
    
    def __init__(self, ttl: int = 300):
        self._cache = {}
        self._ttl = ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Получает значение из кеша"""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if (datetime.now() - timestamp).seconds < self._ttl:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Сохраняет значение в кеш"""
        self._cache[key] = (value, datetime.now())
    
    def clear(self):
        """Очищает кеш"""
        self._cache.clear()


async def fetch_with_retry(session, url, method='GET', max_retries=3, **kwargs):
    """Выполняет запрос с повторными попытками"""
    for attempt in range(max_retries):
        try:
            async with session.request(method, url, **kwargs) as response:
                if response.status < 500:
                    return response
                elif attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)
    
    return None


def run_async(coro):
    """Запускает асинхронную функцию из синхронного кода"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Если цикл уже запущен, создаем задачу
            return asyncio.create_task(coro)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)


class AsyncLock:
    """Асинхронный блокировщик"""
    
    def __init__(self):
        self._lock = asyncio.Lock()
    
    async def __aenter__(self):
        await self._lock.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()
    
    async def acquire(self):
        await self._lock.acquire()
    
    def release(self):
        self._lock.release()