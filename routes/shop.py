from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from models.user import User
from routes.auth import get_current_user
from core.database import db
from bson import ObjectId
from pydantic import BaseModel

router = APIRouter(prefix="/shop", tags=["Shop"])

class ShopItem(BaseModel):
    id: str
    name: str
    cost: int
    description: str
    effect_type: str # 'hp_restore', 'shield'

class ItemCreate(BaseModel):
    name: str
    cost: int
    description: str
    effect_type: str

from datetime import datetime

class Purchase(BaseModel):
    id: str
    item_id: str
    item_name: str
    cost: int
    purchased_at: datetime

@router.get("/history", response_model=List[Purchase])
async def get_purchase_history(current_user: User = Depends(get_current_user)):
    """Get purchase history for current user"""
    cursor = db.purchases.find({"user_id": current_user.id}).sort("purchased_at", -1)
    purchases = await cursor.to_list(100)
    
    return [
        Purchase(
            id=str(p["_id"]),
            item_id=p["item_id"],
            item_name=p["item_name"],
            cost=p["cost"],
            purchased_at=p["purchased_at"]
        )
        for p in purchases
    ]

@router.get("/admin/history/{user_id}", response_model=List[Purchase])
async def get_admin_purchase_history(user_id: str, current_user: User = Depends(get_current_user)):
    """Admin only: Get purchase history for a specific user"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
        
    cursor = db.purchases.find({"user_id": user_id}).sort("purchased_at", -1)
    purchases = await cursor.to_list(100)
    
    return [
        Purchase(
            id=str(p["_id"]),
            item_id=p["item_id"],
            item_name=p["item_name"],
            cost=p["cost"],
            purchased_at=p["purchased_at"]
        )
        for p in purchases
    ]

@router.post("/items", status_code=status.HTTP_201_CREATED)
async def create_item(item_in: ItemCreate, current_user: User = Depends(get_current_user)):
    """Admin only: Create a new shop item."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
        
    item_dump = item_in.model_dump()
    result = await db.shop_items.insert_one(item_dump)
    
    # Remove _id (ObjectId) and set id (str)
    item_dump["id"] = str(result.inserted_id)
    if "_id" in item_dump:
        del item_dump["_id"]
        
    return item_dump

@router.get("/items", response_model=List[ShopItem])
async def get_shop_items():
    items = await db.shop_items.find().to_list(100)
    # Convert ObjectId to str
    return [{"id": str(item["_id"]), **item} for item in items]

@router.post("/buy/{item_id}")
async def buy_item(item_id: str, current_user: User = Depends(get_current_user)):
    try:
        # Try ObjectId
        query = {"_id": ObjectId(item_id)}
    except:
        # Fallback to string ID if invalid ObjectId
        query = {"_id": item_id}

    item_data = await db.shop_items.find_one(query)
    if not item_data:
        raise HTTPException(status_code=404, detail="Item not found")
        
    item_cost = item_data["cost"]
    
    if current_user.stats.gold < item_cost:
        raise HTTPException(status_code=400, detail="Not enough gold")
        
    # Deduct Gold
    await db.users.update_one(
        {"_id": current_user.id},
        {"$inc": {"stats.gold": -item_cost}}
    )
    
    # Record Purchase
    purchase_record = {
        "user_id": current_user.id,
        "item_id": item_id,
        "item_name": item_data["name"],
        "cost": item_cost,
        "purchased_at": datetime.utcnow()
    }
    await db.purchases.insert_one(purchase_record)
    
    # Apply Effect (Simple logic for now)
    if item_data.get("effect_type") == "hp_restore":
        # Restore 20 HP, up to max 100
        new_hp = min(100, current_user.stats.hp + 20)
        await db.users.update_one(
            {"_id": current_user.id},
            {"$set": {"stats.hp": new_hp}}
        )
        
    return {"message": f"Bought {item_data['name']}"}

@router.delete("/items/{item_id}")
async def delete_shop_item(item_id: str, current_user: User = Depends(get_current_user)):
    """Admin only: Delete a shop item."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
        
    try:
        query = {"_id": ObjectId(item_id)}
    except:
        query = {"_id": item_id}
        
    result = await db.shop_items.delete_one(query)
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
        
    return {"message": "Item deleted"}
