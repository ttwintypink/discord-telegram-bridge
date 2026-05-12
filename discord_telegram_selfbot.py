import requests
import asyncio
import telegram
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
import json
import time

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DiscordTelegramSelfBot:
    def __init__(self):
        # Discord настройки (токен аккаунта пользователя)
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.DISCORD_SERVER_ID = 1460084815209566443
        self.DISCORD_CHANNEL_ID = 1475098820365914183
        
        # Telegram настройки
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.TELEGRAM_USER_ID = 1805647541
        
        # Telegram бот
        self.telegram_bot = telegram.Bot(token=self.TELEGRAM_TOKEN)
        
        # Discord API заголовки
        self.headers = {
            'Authorization': f'{self.DISCORD_TOKEN}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Хранилище последних сообщений для отслеживания новых
        self.last_message_id = None
        
    def get_discord_messages(self):
        """Получает последние сообщения из Discord канала"""
        try:
            url = f"https://discord.com/api/v9/channels/{self.DISCORD_CHANNEL_ID}/messages?limit=10"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                messages = response.json()
                return messages
            else:
                logger.error(f"Ошибка получения сообщений: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при запросе к Discord API: {e}")
            return None
    
    async def forward_to_telegram(self, message):
        """Отправляет сообщение в Telegram"""
        try:
            # Получаем время сообщения
            timestamp = message.get('timestamp', '')
            message_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).strftime("%H:%M:%S %d.%m.%Y")
            
            # Получаем информацию об авторе
            author = message.get('author', {})
            author_name = author.get('username', 'Unknown')
            author_display_name = author.get('global_name', author_name)
            
            # Получаем контент сообщения
            content = message.get('content', '')
            
            # Формируем красивое сообщение для Telegram
            telegram_message = f"""
📨 **Новое сообщение из Discord**

👤 *Автор:* {author_display_name} (@{author_name})
⏰ *Время отправки:* {message_time}

💬 *Сообщение:*
> {content}
            """
            
            # Добавляем информацию о вложениях
            attachments = message.get('attachments', [])
            if attachments:
                telegram_message += "\n\n📎 *Вложения:*\n"
                for attachment in attachments:
                    telegram_message += f"• {attachment.get('url', 'No URL')}\n"
            
            # Отправляем сообщение в Telegram
            await self.telegram_bot.send_message(
                chat_id=self.TELEGRAM_USER_ID,
                text=telegram_message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Сообщение от {author_display_name} переслано в Telegram")
            
        except Exception as e:
            logger.error(f"Ошибка при пересылке сообщения в Telegram: {e}")
    
    async def check_new_messages(self):
        """Проверяет новые сообщения и пересылает их"""
        messages = self.get_discord_messages()
        
        if not messages:
            return
        
        # Сортируем сообщения по времени (новые первые)
        messages.sort(key=lambda x: x.get('id', '0'), reverse=True)
        
        # Если это первый запуск, устанавливаем последнее сообщение
        if self.last_message_id is None:
            self.last_message_id = messages[0].get('id') if messages else None
            return
        
        # Ищем новые сообщения
        new_messages = []
        for message in messages:
            message_id = message.get('id')
            if message_id and int(message_id) > int(self.last_message_id):
                new_messages.append(message)
        
        # Пересылаем новые сообщения в обратном порядке (старые → новые)
        for message in reversed(new_messages):
            await self.forward_to_telegram(message)
        
        # Обновляем ID последнего сообщения
        if new_messages:
            self.last_message_id = new_messages[-1].get('id')
    
    async def start_monitoring(self):
        """Запускает мониторинг канала"""
        logger.info("Запуск мониторинга Discord канала...")
        logger.info(f"Сервер: {self.DISCORD_SERVER_ID}")
        logger.info(f"Канал: {self.DISCORD_CHANNEL_ID}")
        
        # Проверяем подключение к Discord
        test_messages = self.get_discord_messages()
        if test_messages is None:
            logger.error("Не удалось подключиться к Discord. Проверьте токен.")
            return
        
        logger.info("Успешное подключение к Discord API")
        
        # Основной цикл мониторинга
        while True:
            try:
                await self.check_new_messages()
                await asyncio.sleep(5)  # Проверка каждые 5 секунд
                
            except KeyboardInterrupt:
                logger.info("Мониторинг остановлен вручную")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                await asyncio.sleep(10)  # Пауза при ошибке

def main():
    bot = DiscordTelegramSelfBot()
    
    try:
        asyncio.run(bot.start_monitoring())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")

if __name__ == "__main__":
    main()
