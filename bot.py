import asyncio
import logging
import sqlite3
import requests
import feedparser
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import os
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# КЛАСС ДЛЯ РАБОТЫ С RSS (Telegram каналы)
# ============================================

class TelegramRSSCollector:
    def __init__(self):
        self.init_database()
        self.rss_server = os.environ.get('RSS_SERVER', 'http://tg-to-rss:3042')
        self.session = requests.Session()
    
    def init_database(self):
        """Инициализация базы данных для отслеживания отправленных постов"""
        try:
            conn = sqlite3.connect('/data/telegram_posts.db')
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS sent_posts
                         (post_id TEXT PRIMARY KEY, 
                          channel_name TEXT,
                          title TEXT,
                          url TEXT,
                          sent_date TEXT)''')
            conn.commit()
            conn.close()
            logger.info("✅ База данных инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
    
    def is_post_sent(self, post_id):
        """Проверка, отправляли ли уже этот пост"""
        try:
            conn = sqlite3.connect('/data/telegram_posts.db')
            c = conn.cursor()
            c.execute("SELECT post_id FROM sent_posts WHERE post_id=?", (post_id,))
            result = c.fetchone()
            conn.close()
            return result is not None
        except:
            return False
    
    def mark_post_sent(self, post_id, channel_name, title, url):
        """Отметить пост как отправленный"""
        try:
            conn = sqlite3.connect('/data/telegram_posts.db')
            c = conn.cursor()
            c.execute(
                "INSERT OR IGNORE INTO sent_posts (post_id, channel_name, title, url, sent_date) VALUES (?, ?, ?, ?, ?)",
                (post_id, channel_name, title, url, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения в БД: {e}")
    
    def get_telegram_channels(self):
        """Получить список доступных Telegram каналов из RSS сервера"""
        try:
            response = self.session.get(f"{self.rss_server}/")
            if response.status_code == 200:
                # Здесь нужно парсить страницу со списком каналов
                # Но проще - дать пользователю возможность добавлять вручную
                return []
        except:
            return []
    
    def parse_telegram_rss(self, rss_url, channel_name):
        """Парсинг RSS ленты Telegram канала"""
        try:
            logger.info(f"📡 Парсинг Telegram канала {channel_name}...")
            
            feed = feedparser.parse(rss_url)
            posts = []
            
            for entry in feed.entries[:10]:  # Берем последние 10 постов
                # Создаем уникальный ID для поста
                post_id = entry.get('id', entry.get('link', entry.title))
                
                # Извлекаем текст поста
                title = entry.title
                if 'summary' in entry:
                    content = entry.summary
                elif 'description' in entry:
                    content = entry.description
                else:
                    content = title
                
                # Ищем изображение
                image = None
                if 'media_content' in entry:
                    for media in entry.media_content:
                        if media.get('medium') == 'image' or 'image' in media.get('type', ''):
                            image = media.get('url')
                            break
                
                if 'links' in entry:
                    for link in entry.links:
                        if link.get('type', '').startswith('image/'):
                            image = link.get('href')
                            break
                
                posts.append({
                    'id': post_id,
                    'title': title,
                    'content': content[:500],  # Ограничиваем длину
                    'url': entry.get('link', ''),
                    'published': entry.get('published', datetime.now().isoformat()),
                    'image': image,
                    'channel': channel_name
                })
            
            logger.info(f"✅ {channel_name}: найдено {len(posts)} постов")
            return posts
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга {channel_name}: {e}")
            return []

# ============================================
# КОНФИГУРАЦИЯ TELEGRAM КАНАЛОВ ДЛЯ ОТСЛЕЖИВАНИЯ
# ============================================

# Добавьте сюда URL RSS лент ваших Telegram каналов
# Формат: http://tg-to-rss:3042/feed/ID_КАНАЛА
# ID канала можно узнать после авторизации в telegram-to-rss

TELEGRAM_CHANNELS = [
    {
        'id': 'channel_1',
        'name': 'Название канала 1',
        'rss_url': 'http://tg-to-rss:3042/feed/123456789',  # Замените на реальный URL
        'button': '📱 Канал 1'
    },
    {
        'id': 'channel_2',
        'name': 'Название канала 2',
        'rss_url': 'http://tg-to-rss:3042/feed/987654321',  # Замените на реальный URL
        'button': '📱 Канал 2'
    },
]

# ============================================
# TELEGRAM БОТ
# ============================================

class RSSForwardBot:
    def __init__(self, token, channel_id):
        self.token = token
        self.channel_id = channel_id
        self.collector = TelegramRSSCollector()
        self.application = None
        logger.info("✅ Бот инициализирован")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        keyboard = []
        
        # Кнопка для всех каналов
        keyboard.append([InlineKeyboardButton("📢 ВСЕ КАНАЛЫ", callback_data="all")])
        
        # Кнопки для каждого канала
        for i in range(0, len(TELEGRAM_CHANNELS), 2):
            row = []
            row.append(InlineKeyboardButton(
                TELEGRAM_CHANNELS[i]['button'], 
                callback_data=f"channel_{TELEGRAM_CHANNELS[i]['id']}"
            ))
            if i + 1 < len(TELEGRAM_CHANNELS):
                row.append(InlineKeyboardButton(
                    TELEGRAM_CHANNELS[i + 1]['button'], 
                    callback_data=f"channel_{TELEGRAM_CHANNELS[i + 1]['id']}"
                ))
            keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📬 *Пересылка из Telegram каналов*\n\n"
            "Выбери источник для пересылки в канал:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "all":
            await self.publish_all(query, context)
        elif query.data.startswith("channel_"):
            channel_id = query.data.replace("channel_", "")
            await self.publish_channel(query, context, channel_id)
    
    async def publish_channel(self, query, context, channel_id):
        """Публикация постов из одного канала"""
        channel = next((c for c in TELEGRAM_CHANNELS if c['id'] == channel_id), None)
        if not channel:
            return
        
        await query.edit_message_text(f"🔍 Собираю посты из {channel['name']}...")
        
        posts = self.collector.parse_telegram_rss(channel['rss_url'], channel['name'])
        
        if not posts:
            await query.edit_message_text(f"❌ Не удалось получить посты из {channel['name']}")
            return
        
        # Фильтруем только новые посты
        new_posts = [p for p in posts if not self.collector.is_post_sent(p['id'])]
        
        if not new_posts:
            await query.edit_message_text(f"📭 Нет новых постов в {channel['name']}")
            return
        
        await query.edit_message_text(f"📤 Публикую {len(new_posts)} постов...")
        
        published = 0
        for post in new_posts:
            try:
                # Формируем текст поста
                text = f"*{post['title']}*\n\n"
                text += f"{post['content']}\n\n"
                if post['url']:
                    text += f"[🔗 Ссылка на пост]({post['url']})"
                
                # Отправляем с картинкой или без
                if post['image']:
                    await context.bot.send_photo(
                        chat_id=self.channel_id,
                        photo=post['image'],
                        caption=text,
                        parse_mode='Markdown'
                    )
                else:
                    await context.bot.send_message(
                        chat_id=self.channel_id,
                        text=text,
                        parse_mode='Markdown'
                    )
                
                self.collector.mark_post_sent(post['id'], channel['name'], post['title'], post['url'])
                published += 1
                await asyncio.sleep(2)  # Пауза между постами
                
            except Exception as e:
                logger.error(f"❌ Ошибка отправки: {e}")
        
        await query.edit_message_text(f"✅ Опубликовано {published} постов из {channel['name']}")
    
    async def publish_all(self, query, context):
        """Публикация постов из всех каналов"""
        await query.edit_message_text("🔍 Собираю посты из всех каналов...")
        
        total = 0
        results = []
        
        for channel in TELEGRAM_CHANNELS:
            posts = self.collector.parse_telegram_rss(channel['rss_url'], channel['name'])
            
            if not posts:
                results.append(f"❌ {channel['name']}: 0")
                continue
            
            new_posts = [p for p in posts if not self.collector.is_post_sent(p['id'])]
            
            if not new_posts:
                results.append(f"📭 {channel['name']}: нет новых")
                continue
            
            channel_published = 0
            for post in new_posts:
                try:
                    text = f"*{post['title']}*\n\n"
                    text += f"{post['content']}\n\n"
                    if post['url']:
                        text += f"[🔗 Ссылка на пост]({post['url']})"
                    
                    if post['image']:
                        await context.bot.send_photo(
                            chat_id=self.channel_id,
                            photo=post['image'],
                            caption=text,
                            parse_mode='Markdown'
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=self.channel_id,
                            text=text,
                            parse_mode='Markdown'
                        )
                    
                    self.collector.mark_post_sent(post['id'], channel['name'], post['title'], post['url'])
                    channel_published += 1
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка: {e}")
            
            results.append(f"✅ {channel['name']}: {channel_published}")
            total += channel_published
        
        report = "📊 *Результаты*\n\n" + "\n".join(results) + f"\n\n✅ *Всего: {total}*"
        await query.edit_message_text(report, parse_mode='Markdown')
    
    async def run_bot(self):
        """Запуск бота"""
        # Удаляем вебхуки
        temp_app = Application.builder().token(self.token).build()
        await temp_app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Вебхуки удалены")
        
        await asyncio.sleep(1)
        
        # Создаем основное приложение
        self.application = Application.builder().token(self.token).build()
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        logger.info("🚀 Бот запускается...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)
        
        # Бесконечное ожидание
        while True:
            await asyncio.sleep(3600)

# ============================================
# ЗАПУСК
# ============================================

async def main():
    BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID')
    
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден")
        sys.exit(1)
    
    if not CHANNEL_ID:
        logger.error("❌ TELEGRAM_CHANNEL_ID не найден")
        sys.exit(1)
    
    bot = RSSForwardBot(BOT_TOKEN, CHANNEL_ID)
    await bot.run_bot()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
