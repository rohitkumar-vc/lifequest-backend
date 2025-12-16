import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    APP_NAME: str = "LifeQuest"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey123")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Database
    MONGO_URI: str = os.getenv("MONGO_URI", "")
    DB_NAME: str = os.getenv("DB_NAME", "tracker")
    
    # Frontend
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Email (Mailgun)
    MAILGUN_API_KEY: str = os.getenv("MAILGUN_API_KEY", "")
    MAILGUN_DOMAIN: str = os.getenv("MAILGUN_DOMAIN", "") # e.g., sandbox....mailgun.org
    MAIL_FROM: str = os.getenv("MAIL_FROM", "LifeQuest Admin")
    TEMPLATE_FOLDER: str = "templates/email"

    # Game Configuration (Defaults)
    # Scaling XP: Index 0 = Lvl 1->2, Index 1 = Lvl 2->3, etc.
    # Fallback to last value if level exceeds list length.
    LEVEL_XP_THRESHOLDS: list = [
        100,  # Lvl 1 -> 2
        300,  # Lvl 2 -> 3
        600,  # Lvl 3 -> 4
        1000, # Lvl 4 -> 5
        1500, # Lvl 5 -> 6
        2100, # Lvl 6 -> 7
        2800, # Lvl 7 -> 8
        3600, # Lvl 8 -> 9
        4500, # Lvl 9 -> 10
        5500  # Lvl 10 -> 11 (and beyond uses this or scales linearly)
    ]
    GAME_LEVEL_UP_XP: int = 100 # Deprecated but kept for fallback or test references
    
    # Todo Configuration
    TODO_REWARD_GOLD: float = 10.0
    TODO_XP_VALUE: int = 20
    TODO_RENEWAL_FEE_PERCENT: float = 0.10
    TODO_DIFFICULTY_MULTIPLIERS: dict = {"easy": 1, "medium": 2, "hard": 4}
    
    # Daily Configuration
    DAILY_REWARD_GOLD: float = 10.0
    DAILY_XP_VALUE: int = 20

    # Habit Multipliers (Base values for Easy)
    HABIT_GOLD_BASE: float = 1.0
    HABIT_XP_BASE: int = 5
    HABIT_DIFFICULTY_MULTIPLIERS: dict = {"easy": 1, "medium": 2, "hard": 4}
    
    # HP Penalties
    HP_PENALTY_EASY: int = 5
    HP_PENALTY_MEDIUM: int = 10
    HP_PENALTY_HARD: int = 20
    
    # Pydantic Settings Config
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
