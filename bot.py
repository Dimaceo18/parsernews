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
        # Создаем сессию с таймаутами
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        })
        # Настраиваем таймауты
        self.session.mount('https://', requests.adapters.HTTPAdapter(max_retries=2))
        self.session.mount('http://', requests.adapters.HTTPAdapter(max_retries=2))
    
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
        """Парсинг конкретного сайта с защитой от ошибок"""
        try:
            logger.info(f"Парсинг {site_config['name']} - {site_config['url']}")
            
            # Пробуем получить страницу с таймаутом 10 секунд
            response = self.session.get(
                site_config['url'], 
                timeout=10,
                allow_redirects=True
            )
            response.encoding = 'utf-8'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            news_list = site_config['parser'](soup)
            
            logger.info(f"✅ {site_config['name']}: найдено {len(news_list)} новостей")
            return news_list
            
        except requests.exceptions.ConnectTimeout:
            logger.error(f"⏰ Таймаут подключения к {site_config['name']}")
            return []
        except requests.exceptions.ReadTimeout:
            logger.error(f"⏰ Таймаут чтения от {site_config['name']}")
            return []
        except requests.exceptions.ConnectionError:
            logger.error(f"🔌 Ошибка подключения к {site_config['name']}")
            return []
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга {site_config['name']}: {e}")
            return []
    
    def get_article_image(self, url):
        """Получение главного изображения статьи"""
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
# ПАРСЕРЫ (упрощенные и надежные)
# ============================================

def parse_onliner(soup):
    """Парсер Onliner.by"""
    news = []
    try:
        # Ищем все возможные новости
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.text.strip()
            
            # Проверяем, похоже ли на новость
            if '/news/' in href and len(text) > 20:
                if not text.startswith('http'):
                    if href.startswith('/'):
                        href = 'https://people.onliner.by' + href
                    elif not href.startswith('http'):
                        href = 'https://people.onliner.by/' + href
                    
                    # Проверяем, не дубликат ли
                    if not any(n['url'] == href for n in news):
                        news.append({
                            'title': text,
                            'url': href,
                            'site': 'Onliner'
                        })
                        if len(news) >= 10:
                            break
    except Exception as e:
        logger.error(f"Ошибка Onliner: {e}")
    
    return news[:10]

def parse_tochka(soup):
    """Парсер Tochka.by"""
    news = []
    try:
        # Ищем все возможные ссылки на новости
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.text.strip()
            
            if '/news/' in href and len(text) > 15:
                if href.startswith('/'):
                    href = 'https://tochka.by' + href
                elif not href.startswith('http'):
                    href = 'https://tochka.by/' + href
                
                if not any(n['url'] == href for n in news):
                    news.append({
                        'title': text,
                        'url': href,
                        'site': 'Tochka.by'
                    })
                    if len(news) >= 10:
                        break
    except Exception as e:
        logger.error(f"Ошибка Tochka: {e}")
    
    return news[:10]

def parse_sb(soup):
    """Парсер SB.by"""
    news = []
    try:
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.text.strip()
            
            if '/news/' in href and len(text) > 15:
                if href.startswith('/'):
                    href = 'https://www.sb.by' + href
                elif not href.startswith('http'):
                    href = 'https://www.sb.by/' + href
                
                if not any(n['url'] == href for n in news):
                    news.append({
                        'title': text,
                        'url': href,
                        'site': 'SB.by'
                    })
                    if len(news) >= 10:
                        break
    except Exception as e:
        logger.error(f"Ошибка SB: {e}")
    
    return news[:10]

def parse_minsknews(soup):
    """Парсер Minsknews.by"""
    news = []
    try:
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.text.strip()
            
            if len(text) > 20 and not 'minsknews.by' in href:
                if href.startswith('/'):
                    href = 'https://minsknews.by' + href
                elif not href.startswith('http'):
                    href = 'https://minsknews.by/' + href
                
                if not any(n['url'] == href for n in news):
                    news.append({
                        'title': text,
                        'url': href,
                        'site': 'Minsknews.by'
                    })
                    if len(news) >= 10:
                        break
    except Exception as e:
        logger.error(f"Ошибка Minsknews: {e}")
    
    return news[:10]

def parse_times(soup):
    """Парсер Times.by"""
    news = []
    try:
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.text.strip()
            
            if len(text) > 20:
                if href.startswith('/'):
                    href = 'https://times.by' + href
                elif not href.startswith('http'):
                    href = 'https://times.by/' + href
                
                if not any(n['url'] == href for n in news):
                    news.append({
                        'title': text,
                        'url': href,
                        'site': 'Times.by'
                    })
                    if len(news) >= 10:
                        break
    except Exception as e:
        logger.error(f"Ошибка Times: {e}")
    
    return news[:10]

def parse_mlyn(soup):
    """Парсер Mlyn.by"""
    news = []
    try:
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.text.strip()
            
            if len(text) > 20:
                if href.startswith('/'):
                    href = 'https://mlyn.by' + href
                elif not href.startswith('http'):
                    href = 'https://mlyn.by/' + href
                
                if not any(n['url'] == href for n in news):
                    news.append({
                        'title': text,
                        'url': href,
                        'site': 'Mlyn.by'
                    })
                    if len(news) >= 10:
                        break
    except Exception as e:
        logger.error(f"Ошибка Mlyn: {e}")
    
    return news[:10]

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
        
        # Создаем Application
        self.application = Application.builder().token(token).build()
        
        # Добавляем обработчики
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("menu", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        logger.info("✅ Бот инициализирован")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        keyboard = []
        keyboard.append([InlineKeyboardButton("📢 ВСЕ САЙТЫ", callback_data="all")])
        
        # Кнопки по 2 в ряд
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
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "all":
            await self.publish_all(query, context)
        elif query.data.startswith("site_"):
            site_id = query.data.replace("site_", "")
            await self.publish_site(query, context, site_id)
    
    async def publish_site(self, query, context, site_id):
        """Публикация с одного сайта"""
        site = next((s for s in SITES if s['id'] == site_id), None)
        if not site:
            await query.edit_message_text("❌ Ошибка")
            return
        
        await query.edit_message_text(f"🔍 Собираю новости с {site['name']}...")
        
        # Получаем новости
        news_list = self.collector.parse_site(site)
        
        if not news_list:
            await query.edit_message_text(
                f"❌ Не удалось получить новости с {site['name']}\n"
                f"Возможно сайт временно недоступен",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ В меню", callback_data="menu")
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
                f"📭 Нет новых новостей с {site['name']}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ В меню", callback_data="menu")
                ]])
            )
            return
        
        await query.edit_message_text(f"📤 Публикую {len(new_news)} новостей...")
        
        # Публикуем
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
                logger.error(f"Ошибка публикации: {e}")
        
        await query.edit_message_text(
            f"✅ Опубликовано {published} новостей с {site['name']}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ В меню", callback_data="menu")
            ]])
        )
    
    async def publish_all(self, query, context):
        """Публикация со всех сайтов"""
        await query.edit_message_text("🔍 Собираю новости со всех сайтов...\nЭто может занять до 2 минут")
        
        total = 0
        results = []
        
        for site in SITES:
            try:
                news_list = self.collector.parse_site(site)
                
                if not news_list:
                    results.append(f"❌ {site['name']}: ошибка")
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
                
            except Exception as e:
                logger.error(f"Ошибка при обработке {site['name']}: {e}")
                results.append(f"❌ {site['name']}: ошибка")
        
        report = "📊 *Результаты*\n\n" + "\n".join(results) + f"\n\n✅ *Всего: {total}*"
        
        await query.edit_message_text(
            report,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ В меню", callback_data="menu")
            ]])
        )
    
    def run(self):
        """Запуск бота"""
        logger.info("🚀 Бот запускается...")
        
        # Создаем новый event loop для Python 3.14
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.application.run_polling()
        except RuntimeError as e:
            logger.error(f"Ошибка event loop: {e}")
            # Пробуем альтернативный способ
            asyncio.run(self.application.run_polling())

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
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
