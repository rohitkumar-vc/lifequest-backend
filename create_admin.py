import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings
from core.security import get_password_hash
from models.user import User, UserStats

async def create_admin():
    print("Connecting to MongoDB...")
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.DB_NAME]
    
    username = "adminQuest"
    email = "admin@lifequest.app"
    password = "adminQuest"
    
    # Check if exists
    existing_user = await db.users.find_one({"username": username})
    if existing_user:
        print("Admin user already exists.")
        return

    print("Creating admin user...")
    hashed_password = get_password_hash(password)
    
    admin_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role="admin",
        is_active=True,
        stats=UserStats(hp=50, xp=0, gold=0, level=1)
    )
    
    await db.users.insert_one(admin_user.model_dump(by_alias=True, exclude={"id"}))
    print("Admin created successfully!")

if __name__ == "__main__":
    asyncio.run(create_admin())
