# LifeQuest Backend Documentation

## Overview
LifeQuest is a gamified productivity application designed to make habit tracking and task management engaging. The backend is built with **FastAPI** and uses **MongoDB** as the database. It provides a robust API for user authentication, task management (Habits, Dailies, Todos), gamification logic (XP, Gold, Levels), and analytics.

## Technology Stack
- **Framework**: FastAPI (Python 3.10+)
- **Database**: MongoDB (accessed via Motor for async operations)
- **Validation**: Pydantic
- **Authentication**: JWT (JSON Web Tokens) with `python-jose` and `passlib`
- **Email Service**: Mailgun API (via `requests`)
- **Server**: Uvicorn

## Project Structure
```
backend/
├── core/               # Core configuration and utilities
│   ├── config.py       # Settings (Env vars, Game constants)
│   ├── database.py     # MongoDB connection logic
│   ├── security.py     # Password hashing and JWT generation
│   ├── email.py        # Mailgun email integration
│   ├── leveling.py     # Scaling XP and level-up logic
│   └── time_utils.py   # Timezone handling helpers
├── models/             # Pydantic models for data validation
│   ├── user.py         # User and UserStats models
│   ├── task.py         # Task models (Habit, Daily, Todo)
│   ├── shop.py         # Shop item models
│   └── analytics.py    # Activity log models
├── routes/             # API Endpoints
│   ├── auth.py         # Login, Register, Profile, Admin Invite
│   ├── tasks.py        # Task CRUD and specialized toggle logic
│   ├── shop.py         # Shop item management and purchase logic
│   └── analytics.py    # Captain's Log (Activity History)
├── templates/          # HTML templates for emails
├── main.py             # Application entry point (CORS, Route inclusion)
└── create_admin.py     # Script to seed an initial admin user
```

## Key Logic & Design Decisions

### 1. Gamification Engine
The core of LifeQuest is its gamification system. User stats (`hp`, `xp`, `gold`, `level`) are central to every action.
- **Leveling**: We use a scaling XP system where each level requires progressively more XP. This is handled by `calculate_new_level_and_xp` in `core/leveling.py`.
- **Rewards**: 
    - **Todos**: Grant Gold and XP upon completion. Can be "undone" (toggled), which reverts rewards.
    - **Habits**: Can be Good (Positive) or Bad (Negative). Positive habits grant rewards; Negative habits deduct HP. Streak multipliers apply to rewards.
    - **Dailies**: Must be done every day. Grant rewards on completion. (Future: Penalties for missed dailies via scheduler).

### 2. Authentication & Security
- **JWT**: A stateless authentication mechanism. Access tokens are short-lived (30 mins), while refresh tokens are long-lived (7 days).
- **Self-Healing Data**: The `/auth/me` endpoint includes logic to automatically fix inconsistent data (e.g., outdated `max_xp` values) when a user logs in, ensuring backward compatibility without complex migration scripts.
- **Admin Registration**: Registration is restricted. Only Admins can invite/create new users via the Admin Dashboard. New users are created with a default password (`Test1234`) and receive an email invitation.

### 4. Habit System (Gamified Logic)
The Habit System uses a **4-State Logic** engine to enforce Positive (Building) and Negative (Breaking) behaviors.

#### Data Model (`models/habit.py`)
Habits are stored in a dedicated `habits` collection.
```python
class Habit(BaseModel):
    title: str
    type: str         # 'positive' | 'negative'
    difficulty: str   # 'easy' | 'medium' | 'hard'
    current_streak: int
    best_streak: int
    milestones: List[Milestone]
```

#### The 4-State Trigger Logic (`POST /habits/{id}/trigger`)
| Type | Action | Intent | Effect |
| :--- | :--- | :--- | :--- |
| **Positive** | **Success** | Performed good habit | +XP, +Gold, Streak++ |
| **Positive** | **Failure** | Skipped good habit | -HP, Streak Reset |
| **Negative** | **Success** | Resisted bad habit | +XP, +Gold, Streak++ |
| **Negative** | **Failure** | Indulged bad habit | -HP, Streak Reset |

#### Milestones
The system automatically checks for milestones (7, 21, 30, 66 days) on every success trigger. Unlocking a milestone grants bonus XP/Gold and adds a badge to the habit.

> **Note**: Milestone rewards are scaled by the Habit's difficulty:
> *   **Easy**: 1x
> *   **Medium**: 1.5x
> *   **Hard**: 2x

### 5. Task Management (Dailies, Todos)

### 4. Shop & Inventory
- Users can spend Gold to buy items.
- **Atomic Transactions**: Purchases prevent negative gold balance.
- **Admin Control**: Admins can dynamically add new items to the global shop.

## API Endpoints Summary

### Authentication (`/auth`)
- `POST /login`: Get Access and Refresh tokens.
- `POST /refresh`: Get a new Access token using a Refresh token.
- `GET /me`: Get current user profile (with auto-healing stats).
- `POST /admin/register-user`: (Admin only) Create a new user account.

### Tasks (`/tasks`)
- `GET /`: List all tasks for the user.
- `POST /`: Create a new task.
- `POST /{id}/complete`: Toggle status for Todos.
- `POST /{id}/habit-toggle`: Trigger a positive/negative habit or undo.
- `POST /{id}/daily-toggle`: Mark a daily as done/undone.
- `DELETE /{id}`: Remove a task.

### Shop (`/shop`)
- `GET /items`: List available items.
- `POST /purchase/{item_id}`: Buy an item.
- `POST /items`: (Admin only) Add a new item to the shop.

### Analytics (`/analytics`)
- `GET /logs`: Retrieve the user's activity history (Captain's Log).

## Setup & Running

1. **Environment Variables**: Create a `.env` file in `backend/`:
   ```env
   # Database
   MONGODB_URL=mongodb://localhost:27017
   DB_NAME=lifequest

   # Security
   SECRET_KEY=your_secret_key_here
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=30

   # Mailgun (Email)
   MAILGUN_API_KEY=your_key
   MAILGUN_DOMAIN=your_domain
   MAIL_FROM=LifeQuest Admin
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
