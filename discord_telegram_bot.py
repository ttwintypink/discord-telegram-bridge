import discord
import asyncio
import telegram
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
import json

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DiscordTelegramBot:
    def __init__(self):
        # Discord настройки (используем токен аккаунта пользователя)
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.DISCORD_SERVER_ID = 1460084815209566443
        self.DISCORD_CHANNEL_ID = 1475098820365914183
        
        # Telegram настройки
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.TELEGRAM_USER_ID = 1805647541
        
        # Инициализация клиентов
        # Используем Account для self-bot
        self.discord_client = discord.Client()
        self.telegram_bot = telegram.Bot(token=self.TELEGRAM_TOKEN)
        
        # Регистрация обработчиков событий
        self.setup_discord_events()
    
    def setup_discord_events(self):
        @self.discord_client.event
        async def on_ready():
            logger.info(f'Discord аккаунт подключен как {self.discord_client.user}')
            logger.info(f'Отслеживание сервера: {self.DISCORD_SERVER_ID}')
            logger.info(f'Отслеживание канала: {self.DISCORD_CHANNEL_ID}')
        
        @self.discord_client.event
        async def on_message(message):
            # Игнорируем свои собственные сообщения
            if message.author == self.discord_client.user:
                return
            
            # Проверяем, что сообщение из нужного канала и сервера
            if (message.channel.id == self.DISCORD_CHANNEL_ID and 
                message.guild.id == self.DISCORD_SERVER_ID):
                
                await self.forward_to_telegram(message)
    
    async def forward_to_telegram(self, discord_message):
        try:
            # Получаем время отправки сообщения
            message_time = discord_message.created_at.strftime("%H:%M:%S %d.%m.%Y")
            
            # Формируем текст сообщения
            author_name = discord_message.author.display_name
            content = discord_message.content
            
            # Формируем красивое сообщение для Telegram
            telegram_message = f"""
📨 **Новое сообщение из Discord**

👤 *Автор:* {author_name}
⏰ *Время отправки:* {message_time}

💬 *Сообщение:*
> {content}
            """
            
            # Добавляем информацию о вложениях, если есть
            if discord_message.attachments:
                telegram_message += "\n\n📎 *Вложения:*\n"
                for attachment in discord_message.attachments:
                    telegram_message += f"• {attachment.url}\n"
            
            # Отправляем сообщение в Telegram
            await self.telegram_bot.send_message(
                chat_id=self.TELEGRAM_USER_ID,
                text=telegram_message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Сообщение от {author_name} переслано в Telegram")
            
        except Exception as e:
            logger.error(f"Ошибка при пересылке сообщения в Telegram: {e}")
    
    async def start(self):
        # Запускаем Discord бота
        await self.discord_client.start(self.DISCORD_TOKEN)

def main():
    bot = DiscordTelegramBot()
    
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")

if __name__ == "__main__":
    main()
