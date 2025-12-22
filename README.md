# LifeQuest Backend Documentation

## Overview
LifeQuest is a gamified productivity application designed to make habit tracking and task management engaging. The backend is built with **FastAPI** and uses **MongoDB** as the database. It provides a robust API for user authentication, task management (Habits, Dailies, Todos), gamification logic (XP, Gold, Levels), and analytics.

## Technology Stack
- **Framework**: FastAPI (Python 3.10+)
- **Database**: MongoDB (accessed via Motor for async operations)
- **Validation**: Pydantic V2
- **Authentication**: JWT (JSON Web Tokens) with `python-jose` and `passlib`
- **Scheduler**: Serverless scheduling via **QStash** (for Todo deadlines)
- **Email Service**: Mailgun API (via `requests`)
- **Server**: Uvicorn

## Project Structure
```
backend/
├── core/               # Core configuration and utilities
│   ├── config.py       # Settings (Env vars, Game constants)
│   ├── database.py     # MongoDB connection logic (PyObjectId Pydantic V2)
│   ├── security.py     # Password hashing and JWT generation
│   ├── leveling.py     # Scaling XP and level-up logic
│   └── time_utils.py   # Timezone handling helpers (IST default)
├── models/             # Pydantic models for data validation
│   ├── user.py         # User and UserStats models
│   ├── todo.py         # Todo model (deadlines, economy, QStash)
│   ├── habit.py        # Habit model
│   ├── task.py         # Legacy/Generic Task models
│   └── ...
├── routes/             # API Endpoints
│   ├── auth.py         # Login, Register, Profile
│   ├── todos.py        # Todo creation, completion, renewal, webhooks
│   ├── habits.py       # Habit tracking logic
│   ├── tasks.py        # Dailies
│   └── ...
├── utils/
│   └── scheduler.py    # QStash integration logic
├── main.py             # Application entry point
└── requirements.txt    # Python dependencies
```

## Key Logic & Design Decisions

### 1. Gamification Engine
User stats (`hp`, `xp`, `gold`, `level`) are central to every action.
- **Leveling**: Scaling XP system.
- **Economy**: Gold is stored strictly as **Integers** to prevent floating-point errors.

### 2. The "Todo Bet" System (Dedicated `todos` collection)
Todos are no longer simple checkboxes; they are "Bets" on your productivity.
- **Creation**:
    - If a **Deadline** is set, you receive the Gold Reward **UPFRONT** (as a Loan).
    - A serverless webhook is scheduled via **QStash** for the exact deadline time.
- **Completion**:
    - If completed before the deadline, you keep the loan AND get a completion bonus (plus XP).
- **Overdue (The Validation Webhook)**:
    - If the deadline hits and the task is active, QStash hits `/check_validity`.
    - **Penalty**: You lose **2x** the Upfront Gold (Repaying the loan + paying a fine).
- **Renewal**:
    - An overdue task can be renewed for a fee (10% of reward) to set a new deadline.

### 3. Habit System
Uses a **4-State Logic** engine for Building (+) and Breaking (-) habits.
- **Positive**: Success (+XP/Gold), Fail (-HP).
- **Negative**: Resisted (+XP/Gold), Indulged (-HP).
- **Milestones**: Automatic bonuses at streak intervals (7, 21, 30 days).

### 4. Scheduler (QStash)
- Instead of a running background process (Celery), we use **Upstash QStash**.
- When a Todo is created, we publish a message to QStash with a `not_before` timestamp.
- QStash calls our webhook `POST /todos/check_validity/{id}` at the exact time.
- Security: The webhook is protected by a custom `CROSS_SITE_API_KEY` Bearer token.

## API Endpoints Summary

### Todos (`/todos`)
- `POST /`: Create a Todo (starts the Bet/Loan logic).
- `PUT /{id}`: Update details. Reschedules if deadline changes.
- `POST /{id}/complete`: Mark done, cancel schedule, award XP.
- `DELETE /{id}`: Delete. (Free if completed, Repays loan if active).
- `POST /{id}/renew`: Pay 10% fee to reschedule overdue item.
- `POST /check_validity/{id}`: (Webhook) Triggers Overdue state and Penalty.

### Habits (`/habits`)
- `POST /`: Create Habit.
- `POST /{id}/trigger`: Log an action (Positive/Negative).

## Setup & Running

1. **Environment Variables**: Create a `.env` file in `backend/`:
   ```env
   # Database
   MONGODB_URL=mongodb://localhost:27017
   DB_NAME=lifequest

   # Security
   SECRET_KEY=your_secret_key_here
   ALGORITHM=HS256
   
   # QStash (Required for Todos)
   QSTASH_TOKEN=your_qstash_token
   CROSS_SITE_API_KEY=your_secret_webhook_key
   BACKEND_URL=https://your-public-url.com # for QStash to hit
   
   # Mailgun
   # ...
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Server**:
   ```bash
   python main.py
   # Runs on http://localhost:8000
   ```
