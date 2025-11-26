import sqlite3
from datetime import date, datetime

def init_db():
    conn = sqlite3.connect('achievements.db')
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            achievement_type TEXT,
            points INTEGER,
            date DATE
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            challenge_start_date DATE,
            challenge_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def add_achievement(user_id, category, achievement_type, points):
    conn = sqlite3.connect('achievements.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO achievements (user_id, category, achievement_type, points, date)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, category, achievement_type, points, date.today()))
    conn.commit()
    conn.close()

def get_or_create_user(user_id, username, first_name):
    conn = sqlite3.connect('achievements.db')
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    
    if not user:
        cur.execute('''
            INSERT INTO users (user_id, username, first_name, challenge_start_date, challenge_active)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, date.today(), 1))
        conn.commit()
    
    conn.close()

def get_challenge_day(user_id):
    conn = sqlite3.connect('achievements.db')
    cur = conn.cursor()
    
    cur.execute('''
        SELECT challenge_start_date, challenge_active 
        FROM users 
        WHERE user_id = ?
    ''', (user_id,))
    
    result = cur.fetchone()
    conn.close()
    
    if result and result[1]:
        start_date = datetime.strptime(result[0], '%Y-%m-%d').date()
        today = date.today()
        challenge_day = (today - start_date).days + 1
        return challenge_day
    else:
        return None

def deactivate_challenge(user_id):
    conn = sqlite3.connect('achievements.db')
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users 
        SET challenge_active = 0 
        WHERE user_id = ?
    ''', (user_id,))
    
    conn.commit()
    conn.close()