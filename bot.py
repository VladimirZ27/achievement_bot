import logging
import sqlite3
import os
import asyncio
import sys
import time
from datetime import date, datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Conflict, TimedOut, NetworkError
import database
import config

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Ежедневные цели
DAILY_GOALS = {
    'workout': {'name': 'Тренировка', 'points': 10, 'emoji': '💪', 'percent': 15},
    'meditation': {'name': 'Медитация', 'points': 5, 'emoji': '🧘', 'percent': 10},
    'reading': {'name': 'Книга (30 минут)', 'points': 5, 'emoji': '📚', 'percent': 15},
    'steps': {'name': '10.000 шагов', 'points': 10, 'emoji': '🚶', 'percent': 20},
    'chinese': {'name': 'Китайский (1 час)', 'points': 10, 'emoji': '🀅', 'percent': 20},
    'thesis': {'name': 'Диссертация (1 страница)', 'points': 10, 'emoji': '📝', 'percent': 20}
}

# Глобальная переменная для отслеживания подтверждения отказа
challenge_confirmations = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и главное меню"""
    user = update.effective_user
    user_id = user.id
    
    # Регистрируем/получаем пользователя
    database.get_or_create_user(user_id, user.username, user.first_name)
    
    # Получаем день челленджа
    challenge_day = database.get_challenge_day(user_id)
    
    keyboard = [
        ['💪 Тело', '🧠 Разум', '🧘 Медитация'],
        ['📊 Статистика', '🔧 Управление челленджем']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    today = date.today()
    
    # Получаем прогресс за сегодня
    progress_data = await get_daily_progress(user_id, today)
    progress_message = progress_data[0]  # Берем только строку прогресса
    
    # Сообщение о дне челленджа
    challenge_text = ""
    if challenge_day:
        challenge_text = f"🎯 День челленджа: {challenge_day}\n"
    else:
        challenge_text = "🎯 Челендж завершен\n"
    
    welcome_text = (
        f"Привет! Я твой помощник по отслеживанию достижений! 🎯\n"
        f"Сегодня: {today.strftime('%d.%m.%Y')}\n"
        f"{challenge_text}\n"
        f"{progress_message}"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def get_daily_progress(user_id: int, today: date):
    """Получить прогресс по ежедневным целям"""
    conn = sqlite3.connect('achievements.db')
    cur = conn.cursor()
    
    # Получаем выполненные сегодня достижения
    cur.execute("""
        SELECT achievement_type 
        FROM achievements 
        WHERE user_id = ? AND date = ?
    """, (user_id, today))
    
    completed_tasks = {row[0] for row in cur.fetchall()}
    conn.close()
    
    # Строим сообщение с прогрессом
    progress_text = "📊 Ежедневные цели:\n\n"
    
    completed_percent = 0
    total_goals = len(DAILY_GOALS)
    completed_count = 0
    
    for goal_id, goal_info in DAILY_GOALS.items():
        if goal_id in completed_tasks:
            status = "✅"
            completed_percent += goal_info['percent']
            completed_count += 1
        else:
            status = "⭕"
        
        progress_text += f"{status} {goal_info['emoji']} {goal_info['name']}\n"
    
    progress_text += f"\n📈 Прогресс: {completed_percent}% выполнено"
    
    return progress_text, completed_count, total_goals

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех нажатий на кнопки"""
    user_input = update.message.text
    user_id = update.effective_user.id
    today = date.today()
    
    # Обработка подтверждения отказа от челленджа
    if user_id in challenge_confirmations:
        if user_input == "✅ Да, отказаться":
            database.deactivate_challenge(user_id)
            del challenge_confirmations[user_id]
            await update.message.reply_text(
                "🎯 Челендж завершен! Твои баллы сохранены, но счетчик дней остановлен.\n"
                "Ты всегда можешь начать новый челлендж!",
                reply_markup=ReplyKeyboardMarkup([['/start']], resize_keyboard=True)
            )
            return
        elif user_input == "❌ Нет, продолжить":
            del challenge_confirmations[user_id]
            await start(update, context)
            return
    
    if user_input == "💪 Тело":
        keyboard = [['🚶 10.000 шагов', '💪 Тренировка'], ['← Назад']]
        await show_menu(update, "Что выполнил для тела?", keyboard)
    
    elif user_input == "🧠 Разум":
        keyboard = [['📚 Книга 30 мин', '🀅 Китайский'], ['📝 Диссертация', '← Назад']]
        await show_menu(update, "Что выполнил для разума?", keyboard)
    
    elif user_input == "🧘 Медитация":
        await process_achievement(update, user_id, 'mind', 'meditation', 5, "медитацию")
    
    elif user_input == "🀅 Китайский":
        keyboard = [['🀅 1 час', '🀅 2 часа'], ['← Назад']]
        await show_menu(update, "Сколько времени уделил китайскому?", keyboard)
    
    elif user_input == "📊 Статистика":
        await show_stats_menu(update, user_id)
    
    elif user_input == "🔧 Управление челленджем":
        await show_challenge_management(update, user_id)
    
    # Обработка достижений
    elif user_input == "🚶 10.000 шагов":
        await process_achievement(update, user_id, 'body', 'steps', 10, "10.000 шагов")
    
    elif user_input == "💪 Тренировка":
        await process_achievement(update, user_id, 'body', 'workout', 10, "тренировку")
    
    elif user_input == "📚 Книга 30 мин":
        await process_achievement(update, user_id, 'mind', 'reading', 5, "чтение 30 минут")
    
    elif user_input == "🀅 1 час":
        await process_achievement(update, user_id, 'mind', 'chinese', 10, "китайский язык (1 час)")
    
    elif user_input == "🀅 2 часа":
        await process_achievement(update, user_id, 'mind', 'chinese', 20, "китайский язык (2 часа)")
    
    elif user_input == "📝 Диссертация":
        await process_achievement(update, user_id, 'mind', 'thesis', 10, "страницу диссертации")
    
    elif user_input == "← Назад":
        await start(update, context)
    
    # Обработка управления челленджем
    elif user_input == "❌ Отказаться от челленджа":
        challenge_confirmations[user_id] = True
        keyboard = [['✅ Да, отказаться', '❌ Нет, продолжить']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "⚠️ Вы уверены, что хотите отказаться от челленджа?\n\n"
            "📊 Ваши баллы сохранятся, но счетчик дней остановится.\n"
            "Это действие нельзя отменить!",
            reply_markup=reply_markup
        )
        return
    
    # Обработка меню статистики
    elif user_input == "📈 Статистика за сегодня":
        await show_today_stats(update, user_id)
    
    elif user_input == "📅 История за месяц":
        await show_month_history(update, user_id)
    
    elif user_input == "💰 Общий итог за месяц":
        await show_month_total(update, user_id)

async def process_achievement(update: Update, user_id: int, category: str, achievement_type: str, points: int, achievement_name: str):
    """Обработать достижение и отправить два сообщения"""
    today = date.today()
    
    # Сообщение 1: Подтверждение добавления баллов
    challenge_day = database.get_challenge_day(user_id)
    challenge_text = f"🎯 День {challenge_day}\n" if challenge_day else "🎯 Челендж завершен\n"
    
    achievement_message = f"🎉 За {achievement_name} +{points} баллов!\n{challenge_text}"
    await update.message.reply_text(achievement_message)
    
    # Добавляем достижение в базу
    database.add_achievement(user_id, category, achievement_type, points)
    
    # Небольшая пауза для лучшего UX
    await asyncio.sleep(0.5)
    
    # Сообщение 2: Обновленный прогресс и предложение продолжить
    progress_data = await get_daily_progress(user_id, today)
    progress_message = progress_data[0]
    completed_count = progress_data[1]
    total_goals = progress_data[2]
    
    if completed_count == total_goals:
        # Все достижения выполнены
        completion_message = (
            f"{progress_message}\n\n"
            f"🎊 Так держать, сегодня ты закрыл все достижения! 🎊\n"
            f"Завтра - больше! 🦾"
        )
        await update.message.reply_text(completion_message)
    else:
        # Не все достижения выполнены - предлагаем продолжить
        continue_message = (
            f"{progress_message}\n\n"
            f"Продолжай в том же духе! 💪\n"
            f"Выбери следующее достижение:"
        )
        
        keyboard = [
            ['💪 Тело', '🧠 Разум', '🧘 Медитация'],
            ['📊 Статистика', '← Назад']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(continue_message, reply_markup=reply_markup)

async def show_challenge_management(update: Update, user_id: int):
    """Показать меню управления челленджем"""
    challenge_day = database.get_challenge_day(user_id)
    
    if challenge_day:
        message = f"🎯 Текущий челлендж: День {challenge_day}\n\n"
        message += "Ты можешь отказаться от челленджа, если нужно сделать перерыв.\n"
        message += "Твои баллы сохранятся, но счетчик дней остановится."
        
        keyboard = [['❌ Отказаться от челленджа'], ['← Назад']]
    else:
        message = "🎯 У тебя нет активного челленджа.\n"
        message += "Начни новый челлендж командой /start!"
        
        keyboard = [['← Назад']]
    
    await show_menu(update, message, keyboard)

async def show_stats_menu(update: Update, user_id: int):
    """Показать меню статистики"""
    keyboard = [
        ['📈 Статистика за сегодня', '📅 История за месяц'],
        ['💰 Общий итог за месяц', '← Назад']
    ]
    await show_menu(update, "📊 Выбери тип статистики:", keyboard)

async def show_today_stats(update: Update, user_id: int):
    """Показать статистику за сегодня"""
    conn = sqlite3.connect('achievements.db')
    cur = conn.cursor()
    
    cur.execute("SELECT SUM(points) FROM achievements WHERE user_id = ? AND date = ?", 
                (user_id, date.today()))
    result = cur.fetchone()
    today_points = result[0] if result[0] else 0
    
    cur.execute("""
        SELECT category, SUM(points) 
        FROM achievements 
        WHERE user_id = ? AND date = ? 
        GROUP BY category
    """, (user_id, date.today()))
    category_stats = cur.fetchall()
    
    conn.close()
    
    message = f"📊 Сегодня {date.today().strftime('%d.%m.%Y')}:\n"
    message += f"Всего баллов: {today_points}\n\n"
    
    for category, points in category_stats:
        emoji = "💪" if category == 'body' else "🧠"
        category_name = "Тело" if category == 'body' else "Разум"
        message += f"{emoji} {category_name}: {points} баллов\n"
    
    await update.message.reply_text(message)

async def show_month_history(update: Update, user_id: int):
    """Показать историю за месяц"""
    conn = sqlite3.connect('achievements.db')
    cur = conn.cursor()
    
    cur.execute("""
        SELECT date, SUM(points) as daily_points
        FROM achievements
        WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
        GROUP BY date
        ORDER BY date DESC
    """, (user_id,))
    
    data = cur.fetchall()
    conn.close()
    
    if not data:
        await update.message.reply_text("📅 В этом месяце еще нет достижений!")
        return
    
    current_month = datetime.now().strftime('%B %Y')
    message = f"📅 История за {current_month}:\n\n"
    
    for entry_date, daily_points in data:
        formatted_date = datetime.strptime(entry_date, '%Y-%m-%d').strftime('%d.%m')
        message += f"{formatted_date}: {daily_points} баллов\n"
    
    await update.message.reply_text(message)

async def show_month_total(update: Update, user_id: int):
    """Показать общий итог за месяц"""
    conn = sqlite3.connect('achievements.db')
    cur = conn.cursor()
    
    cur.execute("""
        SELECT SUM(points) FROM achievements
        WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
    """, (user_id,))
    
    result = cur.fetchone()
    month_total = result[0] if result[0] else 0
    conn.close()
    
    current_month = datetime.now().strftime('%B %Y')
    await update.message.reply_text(
        f"💰 Всего в {current_month} набрано: {month_total} баллов!\n"
        f"Так держать! 💥"
    )

async def show_menu(update: Update, text: str, keyboard: list):
    """Показать меню с кнопками"""
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)

# Обработчики ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Ошибка при обработке обновления {update}: {context.error}")

# Простой HTTP сервер без aiohttp
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.handle_request()
    
    def do_HEAD(self):
        """Обработка HEAD запросов для health checks от Render"""
        self.handle_request(head_only=True)
    
    def handle_request(self, head_only=False):
        if self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            if not head_only:
                self.wfile.write('Bot is running! ✅'.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            if not head_only:
                self.wfile.write('404 Not Found'.encode('utf-8'))
    
    def log_message(self, format, *args):
        # Отключаем логирование запросов
        pass

def run_http_server():
    """Запуск HTTP сервера в отдельном потоке"""
    port = int(os.getenv('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    logger.info(f"HTTP сервер запущен на порту {port}")
    server.serve_forever()

def run_sync_bot():
    """Синхронная обертка для запуска бота"""
    # Инициализируем базу данных
    database.init_db()
    
    # Запускаем HTTP сервер в отдельном потоке
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    logger.info("HTTP сервер запущен в отдельном потоке")
    
    # Создаем приложение бота с настройкой соединения
    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .connection_pool_size(8)
        .pool_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .build()
    )
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота с параметрами для избежания конфликтов
    logger.info("Бот запущен! 🚀")
    
    try:
        # Запускаем polling с параметрами
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            poll_interval=0.5,  # Увеличиваем интервал
            timeout=10,
            close_loop=False
        )
    except Exception as e:
        logger.error(f"Ошибка в run_polling: {e}")
        raise

def main():
    """Основная функция для запуска бота"""
    logger.info(f"Запуск бота на Render. PID: {os.getpid()}")
    
    # Ждем перед стартом, чтобы предыдущий процесс мог завершиться
    time.sleep(5)
    
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            logger.info(f"Попытка запуска бота #{retry_count + 1}")
            run_sync_bot()
            
        except Conflict as e:
            logger.warning(f"Конфликт обнаружен. Подождите 30 секунд...")
            retry_count += 1
            if retry_count < max_retries:
                wait_time = 30 * retry_count
                logger.info(f"Ожидание {wait_time} секунд перед повторной попыткой...")
                time.sleep(wait_time)
            else:
                logger.error("Достигнуто максимальное количество попыток")
                break
                
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Сетевая ошибка: {e}. Перезапуск через 10 секунд...")
            retry_count += 1
            time.sleep(10)
            
        except KeyboardInterrupt:
            logger.info("Бот остановлен пользователем")
            break
            
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"Трассировка: {traceback.format_exc()}")
            
            retry_count += 1
            if retry_count < max_retries:
                wait_time = 60 * retry_count
                logger.info(f"Ожидание {wait_time} секунд перед повторной попыткой...")
                time.sleep(wait_time)
            else:
                logger.error("Достигнуто максимальное количество попыток")
                break

if __name__ == '__main__':
    # Устанавливаем обработчик для корректного завершения
    import signal
    
    def signal_handler(signum, frame):
        logger.info(f"Получен сигнал {signum}. Завершаем работу...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Запускаем бота
    main()
