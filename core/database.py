from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings

# URI Provided
URI = settings.MONGO_URI

client = AsyncIOMotorClient(URI)
db = client[settings.DB_NAME]
