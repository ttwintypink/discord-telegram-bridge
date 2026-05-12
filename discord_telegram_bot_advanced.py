import requests
import asyncio
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
import json
import time
import threading

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
        
        # Ссылка на приложение Telegram для отправки сообщений
        self.telegram_app = None
    
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
            
            # Получаем информацию об авторе (используем ник с сервера)
            author = message.get('author', {})
            author_name = author.get('username', 'Unknown')
            # Пытаемся получить ник с сервера, если есть
            member_data = message.get('member', {})
            server_nick = member_data.get('nick')
            author_display_name = server_nick if server_nick else author.get('global_name', author_name)
            
            # Получаем контент сообщения и убираем пинги ролей
            content = message.get('content', '')
            # Убираем пинги ролей (@role)
            import re
            content = re.sub(r'<@&\d+>', '', content)
            # Убираем символ '>' в начале сообщения
            content = content.lstrip('>')
            # Убираем двойные кавычки в конце, если они есть
            if content.endswith('""'):
                content = content[:-2]
            # Убираем лишние пробелы после удаления пингов
            content = content.strip()
            
            # Формируем красивое сообщение для Telegram (без parse_mode для смайликов)
            telegram_message = f"""
📨 Новое сообщение из Discord

👤 Автор: {author_display_name} (@{author_name})
⏰ Время отправки уведомления: {message_time}

💬 Сообщение:
{content}
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
                    if self.telegram_app:
                        await self.telegram_app.bot.send_message(
                            chat_id=recipient_id,
                            text=telegram_message
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
        
        logger.info(f"Получена команда /start от пользователя {user_id} ({user_name})")
        
        try:
            # Удаляем команду /start
            await update.message.delete()
            
            # Сразу подписываем пользователя
            self.subscribers.add(user_id)
            self.save_subscribers()
            
            # Создаем кнопку отписки
            keyboard = [[InlineKeyboardButton("� Отписаться", callback_data="unsubscribe")]]
            text = f"� Вы успешно подписались на уведомления от Discord-сервера '{self.DISCORD_SERVER_NAME}'"
            
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
            
            # Отправляем последние 3 сообщения из Discord для новеньких (только если есть новые)
            # await self.send_recent_messages(user_id)  # Закомментировано, чтобы не спамить старыми сообщениями
            
            logger.info(f"Пользователь {user_id} подписался на уведомления через /start")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /start: {e}")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на инлайн кнопки"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        await query.answer()  # Показываем "загрузку" на кнопке
        
        logger.info(f"Нажата кнопка {query.data} пользователем {user_id}")
        
        try:
            if query.data == "subscribe":
                # Подписка (этот кейс не должен вызываться, но оставим для надежности)
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
                
                # Отправляем последние 3 сообщения из Discord для новеньких (только если есть новые)
                # await self.send_recent_messages(user_id)  # Закомментировано, чтобы не спамить старыми сообщениями
                
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
                
        except Exception as e:
            logger.error(f"Ошибка при обработке кнопки: {e}")
    
    async def handle_all_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик всех сообщений кроме команд"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username
        
        logger.info(f"Получено сообщение от пользователя {user_id} ({user_name})")
        
        try:
            # Удаляем сообщение пользователя
            await update.message.delete()
            
            error_message = "Я бот для уведомлений. Отправлять мне сообщения нельзя. \nИспользуйте команду /start для управления подпиской."
            
            await context.bot.send_message(
                chat_id=user_id,
                text=error_message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Отправлено сообщение об ошибке пользователю {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")
    
    async def send_recent_messages(self, user_id):
        """Отправляет последние 3 сообщения из Discord новому подписчику"""
        messages = self.get_discord_messages()
        
        if messages:
            # Берем последние 3 сообщения
            recent_messages = messages[:3]
            for message in reversed(recent_messages):  # В хронологическом порядке
                await self.forward_to_telegram(message, user_id)
    
    def start_monitoring_sync(self):
        """Запускает мониторинг канала в синхронном режиме"""
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
                # Используем asyncio.run_coroutine_threadsafe для вызова async функции
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.check_new_messages())
                loop.close()
                
                time.sleep(5)  # Проверка каждые 5 секунд
                
            except KeyboardInterrupt:
                logger.info("Мониторинг остановлен вручную")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(10)  # Пауза при ошибке

def main():
    # Создаем экземпляр бота
    bot = DiscordTelegramBot()
    
    # Создаем приложение Telegram
    application = Application.builder().token(bot.TELEGRAM_TOKEN).build()
    
    # Устанавливаем ссылку на приложение для отправки сообщений
    bot.telegram_app = application
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Добавляем обработчик для всех сообщений кроме команд
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_all_messages))
    
    # Запускаем мониторинг Discord в отдельном потоке
    monitor_thread = threading.Thread(target=bot.start_monitoring_sync, daemon=True)
    monitor_thread.start()
    
    logger.info("Запуск Telegram бота...")
    
    try:
        # Запускаем Telegram бота
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")

if __name__ == "__main__":
    main()
