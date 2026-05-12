import requests
import asyncio
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
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

class DiscordTelegramBot:
    def __init__(self):
        # Discord настройки
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.DISCORD_SERVER_ID = 1460084815209566443
        self.DISCORD_CHANNEL_ID = 1475098820365914183
        self.DISCORD_SERVER_NAME = "Ackerman"
        
        # Telegram настройки
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        
        # Discord API заголовки
        self.headers = {
            'Authorization': f'{self.DISCORD_TOKEN}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Хранилище подписчиков и сообщений
        self.subscribers = set()  # ID пользователей, которые подписаны
        self.user_messages = {}  # ID пользователя -> ID сообщения для редактирования
        self.last_message_id = None
        
        # Файл для сохранения подписчиков
        self.subscribers_file = "subscribers.json"
        self.load_subscribers()
    
    def load_subscribers(self):
        """Загружает список подписчиков из файла"""
        try:
            if os.path.exists(self.subscribers_file):
                with open(self.subscribers_file, 'r') as f:
                    data = json.load(f)
                    self.subscribers = set(data.get('subscribers', []))
                logger.info(f"Загружено {len(self.subscribers)} подписчиков")
        except Exception as e:
            logger.error(f"Ошибка загрузки подписчиков: {e}")
    
    def save_subscribers(self):
        """Сохраняет список подписчиков в файл"""
        try:
            with open(self.subscribers_file, 'w') as f:
                json.dump({'subscribers': list(self.subscribers)}, f)
        except Exception as e:
            logger.error(f"Ошибка сохранения подписчиков: {e}")
    
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
    
    async def forward_to_telegram(self, message, user_id=None):
        """Отправляет сообщение в Telegram всем подписчикам или конкретному пользователю"""
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
            
            # Определяем, кому отправлять
            recipients = [user_id] if user_id else list(self.subscribers)
            
            # Отправляем сообщение
            for recipient_id in recipients:
                try:
                    await telegram.Bot(token=self.TELEGRAM_TOKEN).send_message(
                        chat_id=recipient_id,
                        text=telegram_message,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {recipient_id}: {e}")
            
            if user_id:
                logger.info(f"Сообщение от {author_display_name} отправлено пользователю {user_id}")
            else:
                logger.info(f"Сообщение от {author_display_name} отправлено {len(recipients)} подписчикам")
            
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
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username
        
        # Удаляем команду /start
        await update.message.delete()
        
        # Создаем инлайн кнопки
        if user_id in self.subscribers:
            # Пользователь уже подписан
            keyboard = [[InlineKeyboardButton("🔕 Отписаться", callback_data="unsubscribe")]]
            text = f"🔔 Вы уже подписаны на уведомления от Discord-сервера '{self.DISCORD_SERVER_NAME}'"
        else:
            # Пользователь не подписан
            keyboard = [[InlineKeyboardButton("🔔 Подписаться", callback_data="subscribe")]]
            text = f"🔕 Вы не подписаны на уведомления от Discord-сервера '{self.DISCORD_SERVER_NAME}'"
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем сообщение и закрепляем его
        sent_message = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup
        )
        
        # Закрепляем сообщение
        await context.bot.pin_chat_message(
            chat_id=user_id,
            message_id=sent_message.message_id
        )
        
        # Сохраняем ID сообщения для будущего редактирования
        self.user_messages[user_id] = sent_message.message_id
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на инлайн кнопки"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        await query.answer()  # Показываем "загрузку" на кнопке
        
        if query.data == "subscribe":
            # Подписка
            self.subscribers.add(user_id)
            self.save_subscribers()
            
            # Редактируем сообщение
            keyboard = [[InlineKeyboardButton("🔕 Отписаться", callback_data="unsubscribe")]]
            text = f"🔔 Вы успешно подписались на уведомления от Discord-сервера '{self.DISCORD_SERVER_NAME}'"
            
            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info(f"Пользователь {user_id} подписался на уведомления")
            
            # Отправляем последние 3 сообщения из Discord для новеньких
            await self.send_recent_messages(user_id)
            
        elif query.data == "unsubscribe":
            # Отписка
            self.subscribers.discard(user_id)
            self.save_subscribers()
            
            # Редактируем сообщение
            keyboard = [[InlineKeyboardButton("🔔 Подписаться", callback_data="subscribe")]]
            text = f"🔕 Вы успешно отписались от уведомлений от Discord-сервера '{self.DISCORD_SERVER_NAME}'"
            
            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info(f"Пользователь {user_id} отписался от уведомлений")
    
    async def send_recent_messages(self, user_id):
        """Отправляет последние 3 сообщения из Discord новому подписчику"""
        messages = self.get_discord_messages()
        
        if messages:
            # Берем последние 3 сообщения
            recent_messages = messages[:3]
            for message in reversed(recent_messages):  # В хронологическом порядке
                await self.forward_to_telegram(message, user_id)
    
    async def start_monitoring(self):
        """Запускает мониторинг канала"""
        logger.info("Запуск мониторинга Discord канала...")
        logger.info(f"Сервер: {self.DISCORD_SERVER_ID}")
        logger.info(f"Канал: {self.DISCORD_CHANNEL_ID}")
        logger.info(f"Подписчиков: {len(self.subscribers)}")
        
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
    # Создаем экземпляр бота
    bot = DiscordTelegramBot()
    
    # Создаем приложение Telegram
    application = Application.builder().token(bot.TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Запускаем мониторинг Discord в отдельном потоке
    async def run_monitoring():
        await bot.start_monitoring()
    
    # Запускаем бота и мониторинг
    async def run_all():
        # Запускаем мониторинг Discord
        monitor_task = asyncio.create_task(run_monitoring())
        
        # Запускаем Telegram бота
        await application.run_polling()
        
        # При остановке бота останавливаем и мониторинг
        monitor_task.cancel()
    
    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")

if __name__ == "__main__":
    main()
