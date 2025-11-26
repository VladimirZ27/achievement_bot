import logging
import sqlite3
import matplotlib.pyplot as plt
import io
import os
from datetime import date, datetime, time
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import database
import config

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

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
    progress_message = await get_daily_progress(user_id, today)
    
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
    for goal_id, goal_info in DAILY_GOALS.items():
        if goal_id in completed_tasks:
            status = "✅"
            completed_percent += goal_info['percent']
        else:
            status = "⭕"
        
        progress_text += f"{status} {goal_info['emoji']} {goal_info['name']}\n"
    
    progress_text += f"\n📈 Прогресс: {completed_percent}% выполнено"
    
    return progress_text

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
        database.add_achievement(user_id, 'mind', 'meditation', 5)
        await send_achievement_response(update, user_id, "медитацию", 5)
    
    elif user_input == "🀅 Китайский":
        keyboard = [['🀅 1 час', '🀅 2 часа'], ['← Назад']]
        await show_menu(update, "Сколько времени уделил китайскому?", keyboard)
    
    elif user_input == "📊 Статистика":
        await show_stats_menu(update, user_id)
    
    elif user_input == "🔧 Управление челленджем":
        await show_challenge_management(update, user_id)
    
    # Обработка достижений
    elif user_input == "🚶 10.000 шагов":
        database.add_achievement(user_id, 'body', 'steps', 10)
        await send_achievement_response(update, user_id, "10.000 шагов", 10)
    
    elif user_input == "💪 Тренировка":
        database.add_achievement(user_id, 'body', 'workout', 10)
        await send_achievement_response(update, user_id, "тренировку", 10)
    
    elif user_input == "📚 Книга 30 мин":
        database.add_achievement(user_id, 'mind', 'reading', 5)
        await send_achievement_response(update, user_id, "чтение 30 минут", 5)
    
    elif user_input == "🀅 1 час":
        database.add_achievement(user_id, 'mind', 'chinese', 10)
        await send_achievement_response(update, user_id, "китайский язык (1 час)", 10)
    
    elif user_input == "🀅 2 часа":
        database.add_achievement(user_id, 'mind', 'chinese', 20)
        await send_achievement_response(update, user_id, "китайский язык (2 часа)", 20)
    
    elif user_input == "📝 Диссертация":
        database.add_achievement(user_id, 'mind', 'thesis', 10)
        await send_achievement_response(update, user_id, "страницу диссертации", 10)
    
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
    
    elif user_input == "📊 График прогресса":
        await generate_progress_chart(update, user_id)
    
    elif user_input == "💰 Общий итог за месяц":
        await show_month_total(update, user_id)

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

async def send_achievement_response(update: Update, user_id: int, achievement_name: str, points: int):
    """Отправить ответ о достижении и обновленный прогресс"""
    today = date.today()
    
    challenge_day = database.get_challenge_day(user_id)
    challenge_text = f"🎯 День {challenge_day}\n" if challenge_day else "🎯 Челендж завершен\n"
    
    achievement_message = f"🎉 За {achievement_name} +{points} баллов!\n{challenge_text}"
    progress_message = await get_daily_progress(user_id, today)
    
    full_message = f"{achievement_message}\n{progress_message}"
    await update.message.reply_text(full_message)

async def show_stats_menu(update: Update, user_id: int):
    """Показать меню статистики"""
    keyboard = [
        ['📈 Статистика за сегодня', '📅 История за месяц'],
        ['📊 График прогресса', '💰 Общий итог за месяц'],
        ['← Назад']
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

async def generate_progress_chart(update: Update, user_id: int):
    """Сгенерировать и отправить график прогресса"""
    conn = sqlite3.connect('achievements.db')
    cur = conn.cursor()
    
    cur.execute("""
        SELECT date, SUM(points) 
        FROM achievements 
        WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
        GROUP BY date 
        ORDER BY date
    """, (user_id,))
    
    data = cur.fetchall()
    
    if not data:
        await update.message.reply_text("📊 Недостаточно данных для построения графика!")
        conn.close()
        return
    
    dates = [datetime.strptime(row[0], '%Y-%m-%d').strftime('%d.%m') for row in data]
    points = [row[1] for row in data]
    
    plt.figure(figsize=(10, 5))
    plt.plot(dates, points, marker='o', linewidth=2, color='#FF6B6B')
    plt.title('Прогресс за месяц', fontsize=14, fontweight='bold')
    plt.xlabel('Дата')
    plt.ylabel('Баллы')
    plt.xticks(rotation=45)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=80)
    buf.seek(0)
    plt.close()
    
    conn.close()
    
    await update.message.reply_photo(
        photo=buf,
        caption="📈 Твой прогресс за этот месяц!"
    )

async def show_menu(update: Update, text: str, keyboard: list):
    """Показать меню с кнопками"""
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)

def main():
    # Инициализируем базу данных
    database.init_db()
    
    # Создаем приложение бота
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    print("Бот запущен! 🚀")
    application.run_polling()

if __name__ == '__main__':
    main()