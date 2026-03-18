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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            response = requests.get(
                site_config['url'], 
                headers=headers, 
                timeout=15,
                verify=True
            )
            response.encoding = 'utf-8'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Вызываем специфический парсер для сайта
            news_list = site_config['parser'](soup)
            
            logger.info(f"Сайт {site_config['name']}: найдено {len(news_list)} новостей")
            return news_list
            
        except Exception as e:
            logger.error(f"Ошибка парсинга {site_config['name']}: {e}")
            return []
    
    def get_article_image(self, url):
        """Получение главного изображения статьи (упрощенная версия)"""
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем Open Graph изображение
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                return og_image['content']
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения изображения: {e}")
            return None

# ============================================
# ПАРСЕРЫ ДЛЯ КАЖДОГО САЙТА (упрощенные)
# ============================================

def parse_onliner(soup):
    """Парсер Onliner.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-tidings__item')
        
        for article in articles[:10]:
            try:
                title_elem = article.find('a', class_='news-tidings__link')
                if title_elem and title_elem.get('href'):
                    title = title_elem.text.strip()
                    url = title_elem.get('href')
                    
                    if url and not url.startswith('http'):
                        url = 'https://people.onliner.by' + url
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'Onliner'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере Onliner: {e}")
    
    return news

def parse_tochka(soup):
    """Парсер Tochka.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:10]:
            try:
                title_elem = article.find('a', class_='news-item__title')
                
                if title_elem and title_elem.get('href'):
                    title = title_elem.text.strip()
                    url = title_elem.get('href')
                    
                    if url and not url.startswith('http'):
                        url = 'https://tochka.by' + (url if url.startswith('/') else '/' + url)
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'Tochka.by'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере Tochka: {e}")
    
    return news

def parse_sb(soup):
    """Парсер SB.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:10]:
            try:
                title_elem = article.find('a', class_='news-item__title')
                
                if title_elem and title_elem.get('href'):
                    title = title_elem.text.strip()
                    url = title_elem.get('href')
                    
                    if url and not url.startswith('http'):
                        url = 'https://www.sb.by' + (url if url.startswith('/') else '/' + url)
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'SB.by'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере SB: {e}")
    
    return news

def parse_minsknews(soup):
    """Парсер Minsknews.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:10]:
            try:
                title_elem = article.find('a', class_='news-item__title')
                
                if title_elem and title_elem.get('href'):
                    title = title_elem.text.strip()
                    url = title_elem.get('href')
                    
                    if url and not url.startswith('http'):
                        url = 'https://minsknews.by' + (url if url.startswith('/') else '/' + url)
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'Minsknews.by'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере Minsknews: {e}")
    
    return news

def parse_times(soup):
    """Парсер Times.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='post')
        
        for article in articles[:10]:
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
                    
                    news.append({
                        'title': title,
                        'url': url,
                        'site': 'Times.by'
                    })
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка в парсере Times: {e}")
    
    return news

def parse_mlyn(soup):
    """Парсер Mlyn.by"""
    news = []
    try:
        articles = soup.find_all('div', class_='news-item')
        
        for article in articles[:10]:
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
                    
                    news.append({
                        'title': title,
                        'url': url,
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
        
        # Создаем Application
        self.application = Application.builder().token(token).build()
        
        # Настройка handlers
        self.setup_handlers()
        
        logger.info("✅ Бот инициализирован")
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        await self.show_main_menu(update, context)
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /menu"""
        await self.show_main_menu(update, context)
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отображение главного меню"""
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
        
        # Кнопка "Назад" (если это не первое сообщение)
        if update.callback_query:
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = "📬 *Новостной бот Беларуси*\n\n"
        message += "Выбери источник новостей:\n"
        message += "• Нажми на конкретный сайт — получу 10 свежих новостей\n"
        message += "• Нажми 'ВСЕ САЙТЫ' — получу 60 новостей\n\n"
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
        
        if query.data == "back_to_menu":
            await self.show_main_menu(update, context)
        elif query.data == "all_sites":
            await self.publish_all_sites(query, context)
        elif query.data.startswith("site_"):
            site_id = query.data.replace("site_", "")
            await self.publish_site(query, context, site_id)
    
    async def publish_site(self, query, context, site_id):
        """Публикация новостей с одного сайта"""
        site = next((s for s in SITES if s['id'] == site_id), None)
        if not site:
            await query.edit_message_text("❌ Сайт не найден")
            return
        
        # Сообщение о начале
        await query.edit_message_text(
            f"🔍 *Начинаю сбор новостей с {site['name']}...*",
            parse_mode='Markdown'
        )
        
        # Собираем новости
        news_list = self.collector.parse_site(site)
        
        if not news_list:
            await query.edit_message_text(
                f"❌ Не удалось получить новости с {site['name']}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ В меню", callback_data="back_to_menu")
                ]])
            )
            return
        
        # Фильтруем новые
        new_news = []
        for news in news_list:
            if not self.collector.is_news_sent(news['url']):
                new_news.append(news)
        
        if not new_news:
            await query.edit_message_text(
                f"📭 На {site['name']} нет новых новостей",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ В меню", callback_data="back_to_menu")
                ]])
            )
            return
        
        # Обновляем сообщение
        await query.edit_message_text(
            f"📤 *Публикую {len(new_news)} новостей...*",
            parse_mode='Markdown'
        )
        
        # Публикуем
        published = 0
        for news in new_news:
            try:
                image_url = self.collector.get_article_image(news['url'])
                
                post_text = f"*{news['title']}*\n\n"
                post_text += f"[🔗 Читать на {news['site']}]({news['url']})"
                
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
                        parse_mode='Markdown'
                    )
                
                self.collector.mark_news_sent(news['url'], news['title'], news['site'])
                published += 1
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Ошибка публикации: {e}")
        
        # Финальное сообщение
        await query.edit_message_text(
            f"✅ *Готово!*\n\nОпубликовано {published} новостей с {site['name']}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ В меню", callback_data="back_to_menu")
            ]])
        )
    
    async def publish_all_sites(self, query, context):
        """Публикация новостей со всех сайтов"""
        await query.edit_message_text(
            "🔍 *Начинаю сбор новостей со всех сайтов...*",
            parse_mode='Markdown'
        )
        
        total_published = 0
        results = []
        
        for site in SITES:
            news_list = self.collector.parse_site(site)
            
            if not news_list:
                results.append(f"❌ {site['name']}: 0")
                continue
            
            new_news = []
            for news in news_list:
                if not self.collector.is_news_sent(news['url']):
                    new_news.append(news)
            
            if not new_news:
                results.append(f"📭 {site['name']}: нет новых")
                continue
            
            site_published = 0
            for news in new_news:
                try:
                    image_url = self.collector.get_article_image(news['url'])
                    
                    post_text = f"*{news['title']}*\n\n"
                    post_text += f"[🔗 Читать на {news['site']}]({news['url']})"
                    
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
                            parse_mode='Markdown'
                        )
                    
                    self.collector.mark_news_sent(news['url'], news['title'], news['site'])
                    site_published += 1
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Ошибка: {e}")
            
            results.append(f"{site['color']} {site['name']}: {site_published}")
            total_published += site_published
        
        # Отчет
        report = "📊 *Результаты*\n\n"
        report += "\n".join(results)
        report += f"\n\n✅ *Всего: {total_published}*"
        
        await query.edit_message_text(
            report,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ В меню", callback_data="back_to_menu")
            ]])
        )
    
    def run(self):
        """Запуск бота"""
        logger.info("🚀 Бот запускается...")
        self.application.run_polling(drop_pending_updates=True)

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
