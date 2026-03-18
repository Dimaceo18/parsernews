import asyncio
import logging
import sqlite3
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from telegram import Bot
from telegram.error import TelegramError
import os
import signal
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class NewsParserBot:
    def __init__(self, bot_token, channel_id):
        self.bot = Bot(token=bot_token)
        self.channel_id = channel_id
        self.running = True
        self.init_database()
        
        # Настройка graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
        
    def shutdown(self, signum, frame):
        """Корректное завершение работы"""
        logger.info("Получен сигнал завершения, останавливаю бота...")
        self.running = False
        
    def init_database(self):
        """Инициализация SQLite с индексами для скорости"""
        conn = sqlite3.connect('news.db')
        c = conn.cursor()
        
        # Основная таблица
        c.execute('''CREATE TABLE IF NOT EXISTS sent_news
                     (url TEXT PRIMARY KEY, 
                      title TEXT, 
                      site_name TEXT,
                      published_date TEXT,
                      sent_date TEXT,
                      UNIQUE(url))''')
        
        # Индекс для быстрого поиска по дате
        c.execute('''CREATE INDEX IF NOT EXISTS idx_sent_date 
                     ON sent_news(sent_date)''')
        
        # Индекс для поиска по сайту
        c.execute('''CREATE INDEX IF NOT EXISTS idx_site 
                     ON sent_news(site_name)''')
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    
    def clean_old_news(self, days=30):
        """Очистка старых записей из БД"""
        try:
            conn = sqlite3.connect('news.db')
            c = conn.cursor()
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            c.execute("DELETE FROM sent_news WHERE sent_date < ?", (cutoff,))
            deleted = c.rowcount
            conn.commit()
            conn.close()
            if deleted > 0:
                logger.info(f"Удалено {deleted} старых записей")
        except Exception as e:
            logger.error(f"Ошибка при очистке БД: {e}")
    
    def parse_site(self, config):
        """Парсинг сайта с обработкой ошибок и прокси"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Connection': 'keep-alive',
            }
            
            # Используем сессию для поддержания соединения
            session = requests.Session()
            session.headers.update(headers)
            
            response = session.get(
                config['url'], 
                timeout=config.get('timeout', 15),
                verify=True
            )
            response.encoding = 'utf-8'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            news_list = config['parser'](soup, config)
            
            logger.info(f"Сайт {config['name']}: найдено {len(news_list)} новостей")
            return news_list
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при парсинге {config['name']}: {e}")
        except Exception as e:
            logger.error(f"Ошибка при парсинге {config['name']}: {e}")
        
        return []
    
    def is_news_sent(self, url):
        """Проверка с кэшированием в памяти"""
        conn = sqlite3.connect('news.db')
        c = conn.cursor()
        c.execute("SELECT url FROM sent_news WHERE url=?", (url,))
        result = c.fetchone()
        conn.close()
        return result is not None
    
    def mark_news_sent(self, url, title, site_name, published_date=None):
        """Отметка с датой публикации"""
        conn = sqlite3.connect('news.db')
        c = conn.cursor()
        c.execute(
            """INSERT OR IGNORE INTO sent_news 
               (url, title, site_name, published_date, sent_date) 
               VALUES (?, ?, ?, ?, ?)""",
            (url, title, site_name, 
             published_date or datetime.now().isoformat(),
             datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    
    async def send_news(self, news_item, site_config):
        """Отправка с форматированием под каждый сайт"""
        try:
            # Форматирование сообщения
            if 'format' in site_config:
                message = site_config['format'].format(
                    site_name=site_config['name'],
                    title=news_item['title'],
                    url=news_item['url']
                )
            else:
                message = f"📰 *{site_config['name']}*\n\n"
                message += f"**{news_item['title']}**\n"
                message += f"[Читать далее]({news_item['url']})"
            
            # Добавляем дату если есть
            if 'published' in news_item:
                message += f"\n🕒 {news_item['published']}"
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            
            logger.info(f"✅ Отправлено: {news_item['title'][:50]}...")
            return True
            
        except TelegramError as e:
            logger.error(f"Ошибка Telegram: {e}")
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
        
        return False
    
    async def process_site(self, config):
        """Обработка одного сайта"""
        logger.info(f"🔍 Парсинг {config['name']}...")
        
        news_list = self.parse_site(config)
        sent_count = 0
        
        for news in news_list:
            if not self.is_news_sent(news['url']):
                success = await self.send_news(news, config)
                if success:
                    self.mark_news_sent(
                        news['url'], 
                        news['title'],
                        config['name'],
                        news.get('published')
                    )
                    sent_count += 1
                    await asyncio.sleep(config.get('delay_between_posts', 2))
        
        if sent_count > 0:
            logger.info(f"📤 {config['name']}: отправлено {sent_count} новостей")
        
        return sent_count
    
    async def run(self, sites_config):
        """Основной цикл с проверкой состояния"""
        logger.info("🚀 Бот-парсер запущен")
        
        # Очистка БД при старте
        self.clean_old_news()
        
        while self.running:
            try:
                total_sent = 0
                
                # Парсим все сайты
                for site in sites_config:
                    if not self.running:
                        break
                    
                    sent = await self.process_site(site)
                    total_sent += sent
                    
                    # Пауза между сайтами
                    await asyncio.sleep(site.get('delay_between_sites', 5))
                
                if total_sent > 0:
                    logger.info(f"📊 Итого отправлено: {total_sent} новостей")
                
                # Очистка БД раз в сутки
                if datetime.now().hour == 3:  # В 3 часа ночи
                    self.clean_old_news()
                
                # Ждем до следующего цикла
                wait_time = sites_config[0].get('check_interval', 300)
                logger.info(f"⏳ Ожидание {wait_time} секунд...")
                
                # Ждем с возможностью прерывания
                for _ in range(wait_time):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Критическая ошибка в основном цикле: {e}")
                await asyncio.sleep(60)  # Пауза при ошибке
        
        logger.info("🛑 Бот остановлен")

# Примеры парсеров для разных сайтов
def parse_habr(soup, config):
    """Парсер для Habr"""
    news = []
    articles = soup.find_all('article', class_='post_preview')
    
    for article in articles[:config.get('max_news', 5)]:
        title_elem = article.find('h2')
        link_elem = article.find('a', class_='post__title_link')
        
        if title_elem and link_elem:
            title = title_elem.text.strip()
            url = link_elem.get('href')
            
            # Дата публикации
            date_elem = article.find('span', class_='post__time')
            published = date_elem.text.strip() if date_elem else None
            
            news.append({
                'title': title,
                'url': url,
                'published': published
            })
    
    return news

def parse_tass(soup, config):
    """Парсер для TASS"""
    news = []
    articles = soup.find_all('div', class_='news-item')
    
    for article in articles[:config.get('max_news', 5)]:
        title_elem = article.find('a', class_='news-item__title')
        
        if title_elem:
            title = title_elem.text.strip()
            url = 'https://tass.ru' + title_elem.get('href')
            
            news.append({
                'title': title,
                'url': url
            })
    
    return news

def parse_ria(soup, config):
    """Парсер для РИА Новости"""
    news = []
    articles = soup.find_all('div', class_='list-item')
    
    for article in articles[:config.get('max_news', 5)]:
        title_elem = article.find('a', class_='list-item__title')
        
        if title_elem:
            title = title_elem.text.strip()
            url = title_elem.get('href')
            if not url.startswith('http'):
                url = 'https://ria.ru' + url
            
            news.append({
                'title': title,
                'url': url
            })
    
    return news

# Конфигурация сайтов
SITES_CONFIG = [
    {
        'name': 'Habr',
        'url': 'https://habr.com/ru/news/',
        'parser': parse_habr,
        'max_news': 5,
        'delay_between_posts': 3,
        'delay_between_sites': 10,
        'check_interval': 300,  # 5 минут
        'timeout': 15,
        'format': "📱 *{site_name}*\n\n**{title}**\n[Перейти к новости]({url})"
    },
    {
        'name': 'ТАСС',
        'url': 'https://tass.ru/',
        'parser': parse_tass,
        'max_news': 3,
        'delay_between_posts': 2,
        'delay_between_sites': 10,
        'check_interval': 300,
        'timeout': 15
    },
    # Добавь свои сайты
]

async def main():
    # Берем токен из переменных окружения
    BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '@your_channel')
    
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        sys.exit(1)
    
    bot = NewsParserBot(BOT_TOKEN, CHANNEL_ID)
    
    try:
        await bot.run(SITES_CONFIG)
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
