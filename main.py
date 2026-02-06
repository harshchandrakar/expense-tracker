from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security import HTTPBearer
import os
from datetime import datetime
from typing import List
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv
import pandas as pd
import requests
import jwt
import hashlib

load_dotenv()

app = FastAPI(title="Family Expense API - Google OAuth")
client = MongoClient(os.getenv("MONGO_URI"))
db = client["family_budget"]
security = HTTPBearer()

# Google OAuth Config
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
SECRET_KEY = os.getenv("SECRET_KEY")

class Expense(BaseModel):
    date: datetime
    category: str
    amount: float
    description: str
    is_income: bool = False

class MonthlyIncome(BaseModel):
    month: str  # "2026-02"
    amount: float
    source: str = "Salary"

# User management using Google email as unique ID
async def get_user_from_google(code: str):
    """Exchange Google code for user info"""
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    
    token_response = requests.post(token_url, data=token_data)
    token_json = token_response.json()
    
    if "access_token" not in token_json:
        raise HTTPException(status_code=400, detail="Google auth failed")
    
    # Get user info
    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {token_json['access_token']}"}
    user_response = requests.get(user_info_url, headers=headers)
    user_info = user_response.json()
    
    user_id = user_info.get("email")  # Use email as unique user ID
    user_data = {
        "user_id": user_id,
        "name": user_info.get("name", "Unknown"),
        "email": user_id,
        "picture": user_info.get("picture", "")
    }
    
    # Create user if not exists
    if not db.users.find_one({"user_id": user_id}):
        db.users.insert_one(user_data)
    
    # Generate JWT token
    token = jwt.encode({
        "user_id": user_id,
        "exp": datetime.utcnow().timestamp() + 86400  # 24h
    }, SECRET_KEY, algorithm="HS256")
    
    return {"user": user_data, "token": token}

def get_current_user(token: str = Depends(security)):
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        user = db.users.find_one({"user_id": user_id})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user["user_id"]
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/auth/google/login")
async def google_login():
    """Get Google OAuth URL"""
    google_url = f"""https://accounts.google.com/o/oauth2/v2/auth?
    client_id={GOOGLE_CLIENT_ID}&
    redirect_uri={GOOGLE_REDIRECT_URI}&
    response_type=code&
    scope=openid email profile"""
    return {"login_url": google_url}

@app.get("/auth/google/callback")
async def google_callback(code: str, request: Request):
    """Google OAuth callback"""
    result = await get_user_from_google(code)
    # Redirect to frontend with token
    frontend_url = f"{os.getenv('FRONTEND_URL')}?token={result['token']}"
    return RedirectResponse(url=frontend_url)

# Protected endpoints
@app.post("/income/")
async def add_income(income: MonthlyIncome, user_id: str = Depends(get_current_user)):
    col = db[f"{user_id}_income"]
    col.replace_one({"month": income.month}, income.dict(), upsert=True)
    return {"message": f"Income set for {income.month}"}

@app.get("/income/{month}/")
async def get_income(month: str, user_id: str = Depends(get_current_user)):
    col = db[f"{user_id}_income"]
    inc = col.find_one({"month": month})
    return inc or {"month": month, "amount": 0}

@app.post("/expenses/")
async def add_expense(expense: Expense, user_id: str = Depends(get_current_user)):
    col = db[f"{user_id}_expenses"]
    col.insert_one(expense.dict())
    return {"message": "Added successfully"}

@app.get("/expenses/")
async def get_expenses(year_month: str = None, user_id: str = Depends(get_current_user)):
    col = db[f"{user_id}_expenses"]
    query = {} if not year_month else {"date": {"$regex": year_month}}
    return list(col.find(query))

@app.get("/analytics/monthly/{year_month}/")
async def monthly_analytics(year_month: str, user_id: str = Depends(get_current_user)):
    exp_col = db[f"{user_id}_expenses"]
    inc_col = db[f"{user_id}_income"]
    
    inc_doc = inc_col.find_one({"month": year_month})
    monthly_income = inc_doc["amount"] if inc_doc else 0
    
    df = pd.DataFrame(list(exp_col.find({"date": {"$regex": year_month}})))
    total_expenses = df[~df['is_income']]['amount'].sum() if not df.empty else 0
    surplus = monthly_income - total_expenses
    savings_rate = (surplus / monthly_income * 100) if monthly_income > 0 else 0
    
    top_category = "No expenses"
    if not df.empty and len(df[~df['is_income']]) > 0:
        top_category = df[~df['is_income']].groupby('category')['amount'].sum().idxmax()
    
    return {
        "month": year_month,
        "monthly_income": monthly_income,
        "total_expenses": total_expenses,
        "surplus": surplus,
        "savings_rate": round(savings_rate, 2),
        "top_category": top_category
    }

@app.get("/dashboard/data/")
async def dashboard_data(user_id: str = Depends(get_current_user)):
    col = db[f"{user_id}_expenses"]
    pipeline = [{"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}]
    return list(col.aggregate(pipeline))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
