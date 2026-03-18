import asyncio
import logging
import sqlite3
import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
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
# КЛАСС ДЛЯ РАБОТЫ С НОВОСТЯМИ
# ============================================

class NewsCollector:
    def __init__(self):
        self.init_database()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
    
    def init_database(self):
        try:
            conn = sqlite3.connect('news.db')
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS sent_news
                         (url TEXT PRIMARY KEY, 
                          title TEXT, 
                          site_name TEXT,
                          sent_date TEXT)''')
            conn.commit()
            conn.close()
            logger.info("База данных инициализирована")
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")
    
    def is_news_sent(self, url):
        try:
            conn = sqlite3.connect('news.db')
            c = conn.cursor()
            c.execute("SELECT url FROM sent_news WHERE url=?", (url,))
            result = c.fetchone()
            conn.close()
            return result is not None
        except:
            return False
    
    def mark_news_sent(self, url, title, site_name):
        try:
            conn = sqlite3.connect('news.db')
            c = conn.cursor()
            c.execute(
                "INSERT OR IGNORE INTO sent_news (url, title, site_name, sent_date) VALUES (?, ?, ?, ?)",
                (url, title, site_name, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка сохранения в БД: {e}")
    
    def parse_site(self, site_config):
        try:
            logger.info(f"Парсинг {site_config['name']}...")
            
            response = self.session.get(
                site_config['url'], 
                timeout=15
            )
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            news_list = site_config['parser'](soup)
            
            logger.info(f"{site_config['name']}: найдено {len(news_list)} новостей")
            return news_list
            
        except Exception as e:
            logger.error(f"Ошибка {site_config['name']}: {e}")
            return []
    
    def get_article_image(self, url):
        try:
            response = self.session.get(url, timeout=5)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                return og_image['content']
            
            return None
        except:
            return None

# ============================================
# ПАРСЕР ДЛЯ ONLINER.BY (РАБОЧИЙ ИЗ ДРУГОГО БОТА)
# ============================================

def parse_onliner(soup):
    """Парсер Onliner.by - РАБОТАЕТ (через RSS)"""
    news = []
    try:
        # Используем RSS фид напрямую
        rss_url = "https://www.onliner.by/feed"
        
        response = requests.get(rss_url, timeout=15)
        response.encoding = 'utf-8'
        
        # Парсим XML
        root = ET.fromstring(response.text)
        
        # Ищем все элементы item
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            description = item.findtext("description", "").strip()
            
            # Очищаем описание от HTML
            description = re.sub(r'<[^>]+>', '', description)
            
            # Ищем изображение
            image = ""
            # Пробуем найти enclosure
            enc = item.find("enclosure")
            if enc is not None and enc.get("url"):
                image = enc.get("url")
            
            # Пробуем найти в description
            if not image:
                img_match = re.search(r'<img[^>]+src="([^">]+)"', description)
                if img_match:
                    image = img_match.group(1)
            
            if title and link:
                news.append({
                    'title': title,
                    'url': link,
                    'site': 'Onliner',
                    'description': description[:200],
                    'image': image
                })
                
        logger.info(f"Onliner: найдено {len(news)} новостей через RSS")
        
    except Exception as e:
        logger.error(f"Ошибка Onliner: {e}")
        # Если RSS не работает, пробуем старый метод
        try:
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.text.strip()
                if (len(text) > 30 and 
                    ('onliner.by' in href or '/news/' in href) and
                    not any(n['url'] == href for n in news)):
                    
                    if href.startswith('/'):
                        href = 'https://people.onliner.by' + href
                    
                    news.append({
                        'title': text,
                        'url': href,
                        'site': 'Onliner'
                    })
                    
                    if len(news) >= 10:
                        break
        except:
            pass
    
    return news[:10]

# ============================================
# ПАРСЕР ДЛЯ TIMES.BY (РАБОТАЕТ)
# ============================================

def parse_times(soup):
    """Парсер Times.by - РАБОТАЕТ"""
    news = []
    try:
        articles = soup.find_all('div', class_='post')
        
        for article in articles[:10]:
            title_elem = article.find('a', class_='post-title')
            if not title_elem:
                title_elem = article.find('h2')
                if title_elem:
                    title_elem = title_elem.find('a')
            
            if title_elem:
                title = title_elem.text.strip()
                url = title_elem.get('href')
                
                if url:
                    if url.startswith('/'):
                        url = 'https://times.by' + url
                    
                    if title and url and len(title) > 10:
                        news.append({
                            'title': title,
                            'url': url,
                            'site': 'Times.by'
                        })
    except Exception as e:
        logger.error(f"Ошибка Times.by: {e}")
    
    return news

# ============================================
# ПАРСЕР ДЛЯ MLYN.BY (РАБОТАЕТ)
# ============================================

def parse_mlyn(soup):
    """Парсер Mlyn.by - РАБОТАЕТ"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:10]:
            title_elem = article.find('a', class_='news-title')
            if not title_elem:
                title_elem = article.find('h3')
                if title_elem:
                    title_elem = title_elem.find('a')
            
            if title_elem:
                title = title_elem.text.strip()
                url = title_elem.get('href')
                
                if url:
                    if url.startswith('/'):
                        url = 'https://mlyn.by' + url
                    
                    if title and url and len(title) > 10:
                        news.append({
                            'title': title,
                            'url': url,
                            'site': 'Mlyn.by'
                        })
    except Exception as e:
        logger.error(f"Ошибка Mlyn.by: {e}")
    
    return news

# ============================================
# ПАРСЕР ДЛЯ TOCHKA.BY (ОСТАВЛЯЕМ КАК ЕСТЬ)
# ============================================

def parse_tochka(soup):
    """Парсер Tochka.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:10]:
            title_elem = article.find('a', class_='news-item__title')
            if not title_elem:
                title_elem = article.find('a', class_='post-card__title')
            
            if title_elem:
                title = title_elem.text.strip()
                url = title_elem.get('href')
                
                if url:
                    if url.startswith('/'):
                        url = 'https://tochka.by' + url
                    
                    if title and url and len(title) > 10:
                        news.append({
                            'title': title,
                            'url': url,
                            'site': 'Tochka.by'
                        })
    except Exception as e:
        logger.error(f"Ошибка Tochka: {e}")
    
    return news

# ============================================
# ПАРСЕР ДЛЯ SB.BY (ОСТАВЛЯЕМ КАК ЕСТЬ)
# ============================================

def parse_sb(soup):
    """Парсер SB.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:10]:
            title_elem = article.find('a', class_='news-item__title')
            
            if title_elem:
                title = title_elem.text.strip()
                url = title_elem.get('href')
                
                if url:
                    if url.startswith('/'):
                        url = 'https://www.sb.by' + url
                    
                    if title and url and len(title) > 10:
                        news.append({
                            'title': title,
                            'url': url,
                            'site': 'SB.by'
                        })
    except Exception as e:
        logger.error(f"Ошибка SB.by: {e}")
    
    return news

# ============================================
# ПАРСЕР ДЛЯ MINSKNEWS.BY (ОСТАВЛЯЕМ КАК ЕСТЬ)
# ============================================

def parse_minsknews(soup):
    """Парсер Minsknews.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:10]:
            title_elem = article.find('a', class_='news-item__title')
            if not title_elem:
                title_elem = article.find('a', class_='post-title')
            if not title_elem:
                h3 = article.find('h3')
                if h3:
                    title_elem = h3.find('a')
            
            if title_elem:
                title = title_elem.text.strip()
                url = title_elem.get('href')
                
                if url:
                    if url.startswith('/'):
                        url = 'https://minsknews.by' + url
                    
                    if title and url and len(title) > 10:
                        news.append({
                            'title': title,
                            'url': url,
                            'site': 'Minsknews.by'
                        })
    except Exception as e:
        logger.error(f"Ошибка Minsknews: {e}")
    
    return news

# ============================================
# КОНФИГУРАЦИЯ САЙТОВ
# ============================================

SITES = [
    {'id': 'times', 'name': 'Times.by', 'url': 'https://times.by/', 'parser': parse_times, 'button': '⏱ Times.by'},
    {'id': 'mlyn', 'name': 'Mlyn.by', 'url': 'https://mlyn.by/', 'parser': parse_mlyn, 'button': '🌾 Mlyn.by'},
    {'id': 'onliner', 'name': 'Onliner', 'url': 'https://people.onliner.by/news', 'parser': parse_onliner, 'button': '📱 Onliner'},
    {'id': 'tochka', 'name': 'Tochka.by', 'url': 'https://tochka.by/news/', 'parser': parse_tochka, 'button': '📍 Tochka.by'},
    {'id': 'sb', 'name': 'SB.by', 'url': 'https://www.sb.by/news.html', 'parser': parse_sb, 'button': '📰 SB.by'},
    {'id': 'minsknews', 'name': 'Minsknews.by', 'url': 'https://minsknews.by/', 'parser': parse_minsknews, 'button': '🏙 Minsknews'},
]

# ============================================
# TELEGRAM БОТ
# ============================================

class NewsBot:
    def __init__(self, token, channel_id):
        self.token = token
        self.channel_id = channel_id
        self.collector = NewsCollector()
        self.application = None
        logger.info("✅ Бот инициализирован")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = []
        keyboard.append([InlineKeyboardButton("📢 ВСЕ САЙТЫ", callback_data="all")])
        
        for i in range(0, len(SITES), 2):
            row = []
            row.append(InlineKeyboardButton(SITES[i]['button'], callback_data=f"site_{SITES[i]['id']}"))
            if i + 1 < len(SITES):
                row.append(InlineKeyboardButton(SITES[i + 1]['button'], callback_data=f"site_{SITES[i + 1]['id']}"))
            keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📬 *Новостной бот Беларуси*\n\nВыбери источник новостей:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if query.data == "all":
            await self.publish_all(query, context)
        elif query.data.startswith("site_"):
            site_id = query.data.replace("site_", "")
            await self.publish_site(query, context, site_id)
    
    async def publish_site(self, query, context, site_id):
        site = next((s for s in SITES if s['id'] == site_id), None)
        if not site:
            return
        
        await query.edit_message_text(f"🔍 Собираю новости с {site['name']}...")
        
        news_list = self.collector.parse_site(site)
        
        if not news_list:
            await query.edit_message_text(f"❌ Не удалось получить новости с {site['name']}")
            return
        
        new_news = [n for n in news_list if not self.collector.is_news_sent(n['url'])]
        
        if not new_news:
            await query.edit_message_text(f"📭 Нет новых новостей с {site['name']}")
            return
        
        await query.edit_message_text(f"📤 Публикую {len(new_news)} новостей...")
        
        published = 0
        for news in new_news:
            try:
                image_url = self.collector.get_article_image(news['url'])
                text = f"*{news['title']}*\n\n[🔗 Читать на {news['site']}]({news['url']})"
                
                if image_url:
                    await context.bot.send_photo(
                        chat_id=self.channel_id,
                        photo=image_url,
                        caption=text,
                        parse_mode='Markdown'
                    )
                else:
                    await context.bot.send_message(
                        chat_id=self.channel_id,
                        text=text,
                        parse_mode='Markdown'
                    )
                
                self.collector.mark_news_sent(news['url'], news['title'], news['site'])
                published += 1
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Ошибка: {e}")
        
        await query.edit_message_text(f"✅ Опубликовано {published} новостей с {site['name']}")
    
    async def publish_all(self, query, context):
        await query.edit_message_text("🔍 Собираю новости со всех сайтов...")
        
        total = 0
        results = []
        
        for site in SITES:
            news_list = self.collector.parse_site(site)
            
            if not news_list:
                results.append(f"❌ {site['name']}: 0")
                continue
            
            new_news = [n for n in news_list if not self.collector.is_news_sent(n['url'])]
            
            if not new_news:
                results.append(f"📭 {site['name']}: нет новых")
                continue
            
            site_published = 0
            for news in new_news:
                try:
                    image_url = self.collector.get_article_image(news['url'])
                    text = f"*{news['title']}*\n\n[🔗 Читать на {news['site']}]({news['url']})"
                    
                    if image_url:
                        await context.bot.send_photo(
                            chat_id=self.channel_id,
                            photo=image_url,
                            caption=text,
                            parse_mode='Markdown'
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=self.channel_id,
                            text=text,
                            parse_mode='Markdown'
                        )
                    
                    self.collector.mark_news_sent(news['url'], news['title'], news['site'])
                    site_published += 1
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Ошибка: {e}")
            
            results.append(f"✅ {site['name']}: {site_published}")
            total += site_published
        
        report = "📊 *Результаты*\n\n" + "\n".join(results) + f"\n\n✅ *Всего: {total}*"
        await query.edit_message_text(report, parse_mode='Markdown')
    
    async def run_bot(self):
        """Запуск бота"""
        # Принудительно удаляем все вебхуки
        temp_app = Application.builder().token(self.token).build()
        await temp_app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Вебхуки удалены")
        
        # Небольшая пауза
        await asyncio.sleep(1)
        
        # Создаем новое приложение
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
    CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '@parseranews')
    
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден")
        sys.exit(1)
    
    bot = NewsBot(BOT_TOKEN, CHANNEL_ID)
    await bot.run_bot()

if __name__ == "__main__":
    try:
        # Создаем event loop для Python 3.14
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
