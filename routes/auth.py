from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from datetime import timedelta
from typing import Optional

from core.config import settings
from core.security import create_access_token, verify_password, get_password_hash
from core.database import db
from models.user import User, UserStats
from core.email import send_welcome_email
from models.common import PyObjectId
from bson import ObjectId

router = APIRouter(prefix="/auth", tags=["Auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str

class UserCreate(BaseModel):
    username: str
    email: EmailStr

class PasswordSetup(BaseModel):
    token: str
    password: str

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user_data = await db.users.find_one({"_id": ObjectId(user_id)})
    if user_data is None:
        raise credentials_exception
    return User(**user_data)

class RefreshTokenRequest(BaseModel):
    refresh_token: str

@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    remember_me: bool = False
):
    user_data = await db.users.find_one({"username": form_data.username})
    if not user_data or not verify_password(form_data.password, user_data["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = User(**user_data)
    if not user.is_active:
        raise HTTPException(status_code=400, detail="User not active. Please set your password first.")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )
    
    # Always issue a refresh token
    # If remember_me is True, use long expiration (e.g., 30 days)
    # If False, use standard expiration (e.g., 7 days or 1 day)
    refresh_expires_days = settings.REFRESH_TOKEN_EXPIRE_DAYS if remember_me else 1
    refresh_token_expires = timedelta(days=refresh_expires_days)
    
    refresh_token = create_access_token(
        subject=user.id, expires_delta=refresh_token_expires, refresh=True
    )

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/refresh", response_model=Token)
async def refresh_token_endpoint(request: RefreshTokenRequest):
    refresh_token = request.refresh_token
    credentials_exception = HTTPException(
         status_code=status.HTTP_401_UNAUTHORIZED,
         detail="Could not validate credentials",
         headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        is_refresh: bool = payload.get("refresh", False)
        if user_id is None or not is_refresh:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    # Check if user still exists/active
    user_data = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user_data:
        raise credentials_exception

    # Create new access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user_id, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/admin/register-user")
async def register_user(user_in: UserCreate):
    """Admin creates a user. Generates token. Sends Email."""
    # Check if user exists
    if await db.users.find_one({"email": user_in.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create temp token for password setup (reuse JWT with special scope or just a random string)
    setup_token = create_access_token(subject=user_in.email, expires_delta=timedelta(days=7))
    
    # Create User
    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password="", # No password yet
        is_active=False,
        reset_token=setup_token,
        stats=UserStats()
    )
    
    result = await db.users.insert_one(new_user.model_dump(by_alias=True, exclude={"id"}))
    
    # Send Email
    # Construct link (Frontend URL)
    setup_link = f"http://localhost:5173/setup-password?token={setup_token}"
    try:
        await send_welcome_email(user_in.email, user_in.username, setup_link)
    except Exception as e:
        print(f"Failed to send email: {e}")
        # Continue anyway for dev purposes, but ideally handle this
    
    return {"message": "User created and invitation sent", "user_id": str(result.inserted_id)}

@router.post("/setup-password")
async def setup_password(setup_in: PasswordSetup):
    try:
        payload = jwt.decode(setup_in.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=400, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid token")
        
    user_data = await db.users.find_one({"email": email})
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Ideally verify token matches stored reset_token to prevent reuse if we want strict one-time use
    # But checking email from token is 'okay' for MVP if we assume token is secret provided by email.
    
    hashed_password = get_password_hash(setup_in.password)
    
    await db.users.update_one(
        {"_id": user_data["_id"]},
        {"$set": {"hashed_password": hashed_password, "is_active": True, "reset_token": None}}
    )
    
    return {"message": "Password set successfully. You can now login."}

@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    # Self-healing: Check if max_xp is correct for the current level
    # Use standard logic from config
    level = current_user.stats.level
    
    # Calculate what max_xp SHOULD be
    threshold_index = level - 1
    if threshold_index < len(settings.LEVEL_XP_THRESHOLDS):
        expected_max_xp = settings.LEVEL_XP_THRESHOLDS[threshold_index]
    else:
        expected_max_xp = settings.LEVEL_XP_THRESHOLDS[-1]
        
    # If mismatch, update DB and current object
    if current_user.stats.max_xp != expected_max_xp:
        current_user.stats.max_xp = expected_max_xp
        await db.users.update_one(
             {"_id": current_user.id},
             {"$set": {"stats.max_xp": expected_max_xp}}
        )
        
    return current_user

class UserUpdate(BaseModel):
    email: EmailStr

@router.put("/me", response_model=User)
async def update_user_me(user_update: UserUpdate, current_user: User = Depends(get_current_user)):
    if await db.users.find_one({"email": user_update.email, "_id": {"$ne": ObjectId(current_user.id)}}):
        raise HTTPException(status_code=400, detail="Email already taken")
        
    await db.users.update_one(
        {"_id": current_user.id},
        {"$set": {"email": user_update.email}}
    )
    
    updated_user = await db.users.find_one({"_id": current_user.id})
    return User(**updated_user)

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

@router.post("/change-password")
async def change_password(payload: PasswordChange, current_user: User = Depends(get_current_user)):
    # Verify current password
    user_data = await db.users.find_one({"_id": current_user.id})
    if not verify_password(payload.current_password, user_data["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    # Hash new password
    hashed_password = get_password_hash(payload.new_password)
    
    await db.users.update_one(
        {"_id": current_user.id},
        {"$set": {"hashed_password": hashed_password}}
    )
    
    return {"message": "Password updated successfully"}

@router.delete("/me", status_code=204)
async def delete_user_me(current_user: User = Depends(get_current_user)):
    """
    Delete the current user's account and all associated data.
    Admin users cannot delete themselves via this endpoint to prevent lockout.
    """
    if current_user.role == "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin accounts cannot be deleted directly. Please contact another administrator."
        )

    user_id_str = str(current_user.id)

    # Cascade Delete:
    # 1. Tasks
    await db.tasks.delete_many({"user_id": user_id_str})
    
    # 2. Activity Logs
    await db.activity_logs.delete_many({"user_id": user_id_str})
    
    # 3. The User
    result = await db.users.delete_one({"_id": current_user.id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
        
    return
