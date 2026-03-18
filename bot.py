import asyncio
import logging
import sqlite3
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.ext import Updater  # Явно импортируем
import os
import sys
import warnings

# Подавляем предупреждения
warnings.filterwarnings("ignore")

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
    
    def init_database(self):
        """База данных для отслеживания отправленных новостей"""
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
        """Проверка, не отправляли ли эту новость раньше"""
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
        """Отметить новость как отправленную"""
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
        """Парсинг конкретного сайта"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Connection': 'keep-alive',
            }
            
            session = requests.Session()
            session.headers.update(headers)
            
            response = session.get(
                site_config['url'], 
                timeout=site_config.get('timeout', 15),
                verify=True
            )
            response.encoding = 'utf-8'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Вызываем специфический парсер для сайта
            news_list = site_config['parser'](soup, site_config)
            
            logger.info(f"Сайт {site_config['name']}: найдено {len(news_list)} новостей")
            return news_list
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при парсинге {site_config['name']}: {e}")
        except Exception as e:
            logger.error(f"Ошибка парсинга {site_config['name']}: {e}")
        
        return []
    
    def get_article_image(self, url):
        """Получение главного изображения статьи"""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем Open Graph изображение (стандарт для соцсетей)
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                return og_image['content']
            
            # Ищем Twitter изображение
            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
            if twitter_image and twitter_image.get('content'):
                return twitter_image['content']
            
            # Ищем первое изображение в статье
            article = soup.find('article') or soup.find('div', class_='content') or soup.find('div', class_='post-content')
            if article:
                img = article.find('img')
                if img and img.get('src'):
                    src = img['src']
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        from urllib.parse import urlparse
                        domain = urlparse(url).netloc
                        src = f"https://{domain}{src}"
                    return src
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения изображения {url}: {e}")
            return None

# ============================================
# ПАРСЕРЫ ДЛЯ КАЖДОГО САЙТА
# ============================================

def parse_onliner(soup, config):
    """Парсер Onliner.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-tidings__item')
        
        if not articles:
            articles = soup.find_all('div', class_='b-teasers-news-item')
        
        for article in articles[:config.get('max_news', 10)]:
            try:
                title_elem = article.find('a', class_='news-tidings__link')
                if not title_elem:
                    title_elem = article.find('a', class_='b-teasers-news-item__title')
                
                if title_elem and title_elem.get('href'):
                    title = title_elem.text.strip()
                    url = title_elem.get('href')
                    
                    if url and not url.startswith('http'):
                        url = 'https://people.onliner.by' + url
                    
                    # Краткое описание
                    desc_elem = article.find('div', class_='news-tidings__brief')
                    description = desc_elem.text.strip() if desc_elem else ""
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'description': description,
                        'site': 'Onliner'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере Onliner: {e}")
    
    return news

def parse_tochka(soup, config):
    """Парсер Tochka.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:config.get('max_news', 10)]:
            try:
                title_elem = article.find('a', class_='news-item__title')
                
                if title_elem and title_elem.get('href'):
                    title = title_elem.text.strip()
                    url = title_elem.get('href')
                    
                    if url and not url.startswith('http'):
                        url = 'https://tochka.by' + (url if url.startswith('/') else '/' + url)
                    
                    description = ""
                    desc_elem = article.find('div', class_='news-item__announce')
                    if desc_elem:
                        description = desc_elem.text.strip()
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'description': description,
                        'site': 'Tochka.by'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере Tochka: {e}")
    
    return news

def parse_sb(soup, config):
    """Парсер SB.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:config.get('max_news', 10)]:
            try:
                title_elem = article.find('a', class_='news-item__title')
                
                if title_elem and title_elem.get('href'):
                    title = title_elem.text.strip()
                    url = title_elem.get('href')
                    
                    if url and not url.startswith('http'):
                        url = 'https://www.sb.by' + (url if url.startswith('/') else '/' + url)
                    
                    description = ""
                    desc_elem = article.find('div', class_='news-item__announce')
                    if desc_elem:
                        description = desc_elem.text.strip()
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'description': description,
                        'site': 'SB.by'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере SB: {e}")
    
    return news

def parse_minsknews(soup, config):
    """Парсер Minsknews.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        if not articles:
            articles = soup.find_all('article', class_='post')
        
        for article in articles[:config.get('max_news', 10)]:
            try:
                title_elem = article.find('a', class_='news-item__title')
                if not title_elem:
                    title_elem = article.find('a', class_='post-title')
                
                if title_elem and title_elem.get('href'):
                    title = title_elem.text.strip()
                    url = title_elem.get('href')
                    
                    if url and not url.startswith('http'):
                        url = 'https://minsknews.by' + (url if url.startswith('/') else '/' + url)
                    
                    description = ""
                    desc_elem = article.find('div', class_='news-item__excerpt')
                    if desc_elem:
                        description = desc_elem.text.strip()
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'description': description,
                        'site': 'Minsknews.by'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере Minsknews: {e}")
    
    return news

def parse_times(soup, config):
    """Парсер Times.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='post')
        
        for article in articles[:config.get('max_news', 10)]:
            try:
                title_elem = article.find('a', class_='post-title')
                if not title_elem:
                    h2 = article.find('h2')
                    if h2:
                        title_elem = h2.find('a')
                
                if title_elem and title_elem.get('href'):
                    title = title_elem.text.strip()
                    url = title_elem.get('href')
                    
                    if url and not url.startswith('http'):
                        url = 'https://times.by' + (url if url.startswith('/') else '/' + url)
                    
                    description = ""
                    desc_elem = article.find('div', class_='post-excerpt')
                    if desc_elem:
                        description = desc_elem.text.strip()
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'description': description,
                        'site': 'Times.by'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере Times: {e}")
    
    return news

def parse_mlyn(soup, config):
    """Парсер Mlyn.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:config.get('max_news', 10)]:
            try:
                title_elem = article.find('a', class_='news-title')
                if not title_elem:
                    h3 = article.find('h3')
                    if h3:
                        title_elem = h3.find('a')
                
                if title_elem and title_elem.get('href'):
                    title = title_elem.text.strip()
                    url = title_elem.get('href')
                    
                    if url and not url.startswith('http'):
                        url = 'https://mlyn.by' + (url if url.startswith('/') else '/' + url)
                    
                    description = ""
                    desc_elem = article.find('div', class_='news-description')
                    if desc_elem:
                        description = desc_elem.text.strip()
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'description': description,
                        'site': 'Mlyn.by'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере Mlyn: {e}")
    
    return news

# ============================================
# КОНФИГУРАЦИЯ САЙТОВ
# ============================================

SITES = [
    {
        'id': 'onliner',
        'name': 'Onliner',
        'url': 'https://people.onliner.by/news',
        'parser': parse_onliner,
        'button_text': '📱 Onliner',
        'color': '🟣'
    },
    {
        'id': 'tochka',
        'name': 'Tochka.by',
        'url': 'https://tochka.by/news/',
        'parser': parse_tochka,
        'button_text': '📍 Tochka.by',
        'color': '🔵'
    },
    {
        'id': 'sb',
        'name': 'SB.by',
        'url': 'https://www.sb.by/news.html',
        'parser': parse_sb,
        'button_text': '📰 SB.by',
        'color': '🔴'
    },
    {
        'id': 'minsknews',
        'name': 'Minsknews.by',
        'url': 'https://minsknews.by/',
        'parser': parse_minsknews,
        'button_text': '🏙 Minsknews',
        'color': '🟢'
    },
    {
        'id': 'times',
        'name': 'Times.by',
        'url': 'https://times.by/',
        'parser': parse_times,
        'button_text': '⏱ Times.by',
        'color': '🟡'
    },
    {
        'id': 'mlyn',
        'name': 'Mlyn.by',
        'url': 'https://mlyn.by/',
        'parser': parse_mlyn,
        'button_text': '🌾 Mlyn.by',
        'color': '🟠'
    }
]

# ============================================
# TELEGRAM БОТ
# ============================================

class NewsBot:
    def __init__(self, token, channel_id):
        self.token = token
        self.channel_id = channel_id
        self.collector = NewsCollector()
        
        # Создаем Application с явными параметрами
        builder = Application.builder()
        builder.token(token)
        builder.connect_rate_limit(30)  # Лимиты для избежания блокировки
        builder.write_timeout(30)
        builder.read_timeout(30)
        builder.pool_timeout(30)
        
        self.application = builder.build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("menu", self.show_menu))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        self.application.add_handler(CallbackQueryHandler(self.back_to_menu, pattern="^back_to_menu$"))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        await self.show_main_menu(update, context)
    
    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать главное меню"""
        await self.show_main_menu(update, context)
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отображение главного меню с кнопками"""
        keyboard = []
        
        # Кнопка "Все сайты"
        keyboard.append([InlineKeyboardButton("📢 ВСЕ САЙТЫ (60 новостей)", callback_data="all_sites")])
        
        # Кнопки для каждого сайта (по 2 в ряд)
        for i in range(0, len(SITES), 2):
            row = []
            row.append(InlineKeyboardButton(SITES[i]['button_text'], callback_data=f"site_{SITES[i]['id']}"))
            if i + 1 < len(SITES):
                row.append(InlineKeyboardButton(SITES[i + 1]['button_text'], callback_data=f"site_{SITES[i + 1]['id']}"))
            keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = "📬 *Новостной бот Беларуси*\n\n"
        message += "Выбери источник новостей:\n"
        message += "• Нажми на конкретный сайт — получу 10 свежих новостей\n"
        message += "• Нажми 'ВСЕ САЙТЫ' — получу 60 новостей (по 10 с каждого)\n\n"
        message += "Новости будут опубликованы в канал!"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "all_sites":
            await self.publish_all_sites(query, context)
        elif query.data.startswith("site_"):
            site_id = query.data.replace("site_", "")
            await self.publish_site(query, context, site_id)
    
    async def publish_site(self, query, context, site_id):
        """Публикация новостей с одного сайта"""
        # Находим сайт по ID
        site = next((s for s in SITES if s['id'] == site_id), None)
        if not site:
            await query.edit_message_text("❌ Сайт не найден")
            return
        
        # Отправляем сообщение о начале
        await query.edit_message_text(
            f"🔍 *Начинаю сбор новостей с {site['name']}...*\n\n"
            f"⏳ Подожди немного, я собираю 10 последних новостей",
            parse_mode='Markdown'
        )
        
        # Собираем новости
        news_list = self.collector.parse_site(site)
        
        if not news_list:
            await query.edit_message_text(
                f"❌ Не удалось получить новости с {site['name']}.\n"
                f"Попробуй позже или выбери другой сайт.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ В меню", callback_data="back_to_menu")
                ]])
            )
            return
        
        # Фильтруем только новые (не отправленные ранее)
        new_news = []
        for news in news_list:
            if not self.collector.is_news_sent(news['url']):
                new_news.append(news)
        
        if not new_news:
            await query.edit_message_text(
                f"📭 На {site['name']} нет новых новостей (все уже были отправлены).\n"
                f"Попробуй позже!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ В меню", callback_data="back_to_menu")
                ]])
            )
            return
        
        # Обновляем сообщение
        await query.edit_message_text(
            f"📤 *Публикую {len(new_news)} новостей с {site['name']} в канал...*",
            parse_mode='Markdown'
        )
        
        # Публикуем каждую новость
        published = 0
        for news in new_news:
            try:
                # Получаем изображение для статьи
                image_url = self.collector.get_article_image(news['url'])
                
                # Формируем текст поста
                post_text = f"*{news['title']}*\n\n"
                if news.get('description'):
                    post_text += f"{news['description']}\n\n"
                
                # Добавляем ссылку
                post_text += f"[🔗 Читать полностью на {news['site']}]({news['url']})"
                
                # Отправляем в канал
                if image_url:
                    await context.bot.send_photo(
                        chat_id=self.channel_id,
                        photo=image_url,
                        caption=post_text,
                        parse_mode='Markdown'
                    )
                else:
                    await context.bot.send_message(
                        chat_id=self.channel_id,
                        text=post_text,
                        parse_mode='Markdown',
                        disable_web_page_preview=False
                    )
                
                # Отмечаем как отправленную
                self.collector.mark_news_sent(news['url'], news['title'], news['site'])
                published += 1
                
                # Небольшая задержка между постами
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Ошибка публикации: {e}")
                continue
        
        # Финальное сообщение
        await query.edit_message_text(
            f"✅ *Готово!*\n\n"
            f"Опубликовано {published} новостей с {site['name']} в канал.\n"
            f"{'🆕 Все новости свежие!' if published == len(new_news) else f'⚠️ {len(new_news) - published} не удалось опубликовать'}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ В меню", callback_data="back_to_menu")
            ]])
        )
    
    async def publish_all_sites(self, query, context):
        """Публикация новостей со всех сайтов"""
        await query.edit_message_text(
            "🔍 *Начинаю сбор новостей со всех сайтов...*\n\n"
            "⏳ Это займет около 2-3 минут. Я соберу по 10 новостей с каждого из 6 сайтов.",
            parse_mode='Markdown'
        )
        
        total_published = 0
        results = []
        
        for site in SITES:
            # Собираем новости
            news_list = self.collector.parse_site(site)
            
            if not news_list:
                results.append(f"❌ {site['name']}: 0 новостей")
                continue
            
            # Фильтруем новые
            new_news = []
            for news in news_list:
                if not self.collector.is_news_sent(news['url']):
                    new_news.append(news)
            
            if not new_news:
                results.append(f"📭 {site['name']}: нет новых")
                continue
            
            # Публикуем
            site_published = 0
            for news in new_news:
                try:
                    image_url = self.collector.get_article_image(news['url'])
                    
                    post_text = f"*{news['title']}*\n\n"
                    if news.get('description'):
                        post_text += f"{news['description']}\n\n"
                    post_text += f"[🔗 Читать полностью на {news['site']}]({news['url']})"
                    
                    if image_url:
                        await context.bot.send_photo(
                            chat_id=self.channel_id,
                            photo=image_url,
                            caption=post_text,
                            parse_mode='Markdown'
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=self.channel_id,
                            text=post_text,
                            parse_mode='Markdown',
                            disable_web_page_preview=False
                        )
                    
                    self.collector.mark_news_sent(news['url'], news['title'], news['site'])
                    site_published += 1
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Ошибка: {e}")
                    continue
            
            results.append(f"{site['color']} {site['name']}: {site_published} новостей")
            total_published += site_published
        
        # Финальный отчет
        report = "📊 *Результаты публикации*\n\n"
        report += "\n".join(results)
        report += f"\n\n✅ *Всего опубликовано: {total_published} новостей*"
        
        await query.edit_message_text(
            report,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ В меню", callback_data="back_to_menu")
            ]])
        )
    
    async def back_to_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Возврат в меню"""
        query = update.callback_query
        await query.answer()
        await self.show_main_menu(update, context)
    
    def run(self):
        """Запуск бота"""
        logger.info("🚀 Бот запускается...")
        self.application.run_polling(
            poll_interval=1.0,
            timeout=30,
            drop_pending_updates=True
        )

# ============================================
# ЗАПУСК БОТА
# ============================================

def main():
    # Берем токен из переменных окружения
    BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '@your_channel')
    
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        sys.exit(1)
    
    logger.info(f"Бот запускается с токеном: {BOT_TOKEN[:5]}...")
    logger.info(f"Канал: {CHANNEL_ID}")
    
    try:
        # Создаем и запускаем бота
        bot = NewsBot(BOT_TOKEN, CHANNEL_ID)
        bot.run()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
