import asyncio
import logging
import sqlite3
import requests
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
# ТОЧНЫЕ ПАРСЕРЫ
# ============================================

def parse_onliner(soup):
    """Парсер Onliner.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-tidings__item')
        
        if not articles:
            articles = soup.find_all('div', class_='b-teasers-news-item')
        
        logger.info(f"Onliner: найдено блоков {len(articles)}")
        
        for article in articles[:10]:
            title_elem = article.find('a', class_='news-tidings__link')
            if not title_elem:
                title_elem = article.find('a', class_='b-teasers-news-item__title')
            
            if title_elem:
                title = title_elem.text.strip()
                url = title_elem.get('href')
                
                if url:
                    if url.startswith('/'):
                        url = 'https://people.onliner.by' + url
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'Onliner'
                    })
    except Exception as e:
        logger.error(f"Ошибка Onliner: {e}")
    
    return news

def parse_tochka(soup):
    """Парсер Tochka.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        if not articles:
            articles = soup.find_all('article', class_='post-card')
        
        logger.info(f"Tochka: найдено блоков {len(articles)}")
        
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
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'Tochka.by'
                    })
    except Exception as e:
        logger.error(f"Ошибка Tochka: {e}")
    
    return news

def parse_sb(soup):
    """Парсер SB.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        if not articles:
            articles = soup.find_all('div', class_='b-news-list__item')
        
        logger.info(f"SB.by: найдено блоков {len(articles)}")
        
        for article in articles[:10]:
            title_elem = article.find('a', class_='news-item__title')
            if not title_elem:
                title_elem = article.find('a', class_='b-news-list__link')
            
            if title_elem:
                title = title_elem.text.strip()
                url = title_elem.get('href')
                
                if url:
                    if url.startswith('/'):
                        url = 'https://www.sb.by' + url
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'SB.by'
                    })
    except Exception as e:
        logger.error(f"Ошибка SB.by: {e}")
    
    return news

def parse_minsknews(soup):
    """Парсер Minsknews.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        if not articles:
            articles = soup.find_all('article', class_='post')
        
        logger.info(f"Minsknews: найдено блоков {len(articles)}")
        
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
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'Minsknews.by'
                    })
    except Exception as e:
        logger.error(f"Ошибка Minsknews: {e}")
    
    return news

def parse_times(soup):
    """Парсер Times.by (рабочий)"""
    news = []
    try:
        articles = soup.find_all('div', class_='post')
        
        logger.info(f"Times.by: найдено блоков {len(articles)}")
        
        for article in articles[:10]:
            title_elem = article.find('a', class_='post-title')
            if not title_elem:
                h2 = article.find('h2')
                if h2:
                    title_elem = h2.find('a')
            
            if title_elem:
                title = title_elem.text.strip()
                url = title_elem.get('href')
                
                if url:
                    if url.startswith('/'):
                        url = 'https://times.by' + url
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'Times.by'
                    })
    except Exception as e:
        logger.error(f"Ошибка Times.by: {e}")
    
    return news

def parse_mlyn(soup):
    """Парсер Mlyn.by (рабочий)"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        logger.info(f"Mlyn.by: найдено блоков {len(articles)}")
        
        for article in articles[:10]:
            title_elem = article.find('a', class_='news-title')
            if not title_elem:
                h3 = article.find('h3')
                if h3:
                    title_elem = h3.find('a')
            
            if title_elem:
                title = title_elem.text.strip()
                url = title_elem.get('href')
                
                if url:
                    if url.startswith('/'):
                        url = 'https://mlyn.by' + url
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'Mlyn.by'
                    })
    except Exception as e:
        logger.error(f"Ошибка Mlyn.by: {e}")
    
    return news

# ============================================
# КОНФИГУРАЦИЯ
# ============================================

SITES = [
    {'id': 'onliner', 'name': 'Onliner', 'url': 'https://people.onliner.by/news', 'parser': parse_onliner, 'button': '📱 Onliner'},
    {'id': 'tochka', 'name': 'Tochka.by', 'url': 'https://tochka.by/news/', 'parser': parse_tochka, 'button': '📍 Tochka.by'},
    {'id': 'sb', 'name': 'SB.by', 'url': 'https://www.sb.by/news.html', 'parser': parse_sb, 'button': '📰 SB.by'},
    {'id': 'minsknews', 'name': 'Minsknews.by', 'url': 'https://minsknews.by/', 'parser': parse_minsknews, 'button': '🏙 Minsknews'},
    {'id': 'times', 'name': 'Times.by', 'url': 'https://times.by/', 'parser': parse_times, 'button': '⏱ Times.by'},
    {'id': 'mlyn', 'name': 'Mlyn.by', 'url': 'https://mlyn.by/', 'parser': parse_mlyn, 'button': '🌾 Mlyn.by'}
]

# ============================================
# TELEGRAM БОТ
# ============================================

class NewsBot:
    def __init__(self, token, channel_id):
        self.token = token
        self.channel_id = channel_id
        self.collector = NewsCollector()
        self.application = Application.builder().token(token).build()
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
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
        elif query.data == "menu":
            await self.start_command(update, context)
    
    async def publish_site(self, query, context, site_id):
        site = next((s for s in SITES if s['id'] == site_id), None)
        if not site:
            return
        
        await query.edit_message_text(f"🔍 Собираю новости с {site['name']}...")
        
        news_list = self.collector.parse_site(site)
        
        if not news_list:
            await query.edit_message_text(
                f"❌ Не удалось получить новости с {site['name']}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ В меню", callback_data="menu")
                ]])
            )
            return
        
        new_news = [n for n in news_list if not self.collector.is_news_sent(n['url'])]
        
        if not new_news:
            await query.edit_message_text(
                f"📭 Нет новых новостей с {site['name']}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ В меню", callback_data="menu")
                ]])
            )
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
        
        await query.edit_message_text(
            f"✅ Опубликовано {published} новостей с {site['name']}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ В меню", callback_data="menu")
            ]])
        )
    
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
        
        await query.edit_message_text(
            report,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ В меню", callback_data="menu")
            ]])
        )
    
    def run(self):
        logger.info("🚀 Бот запускается...")
        self.application.run_polling()

# ============================================
# ЗАПУСК
# ============================================

def main():
    BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '@parseranews')
    
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден")
        sys.exit(1)
    
    try:
        bot = NewsBot(BOT_TOKEN, CHANNEL_ID)
        bot.run()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
