import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime
import plotly.graph_objects as go
import pymongo
import os
import requests
import hashlib
import json
from st_pages import Page, show_pages, hide_pages

# Config for Streamlit Cloud
st.set_page_config(
    page_title="Family Budget Tracker", 
    page_icon="💰", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Streamlit Cloud Secrets (auto-loaded)
MONGO_URI = st.secrets["mongo_uri"]
GOOGLE_CLIENT_ID = st.secrets["google_client_id"]
GOOGLE_CLIENT_SECRET = st.secrets["google_client_secret"]

# MongoDB Connection
@st.cache_resource
def init_db():
    client = pymongo.MongoClient(MONGO_URI)
    return client["family_budget"]

client = init_db()
categories = [
    "Food & Groceries", "Utilities (Electricity, Water, Gas)", "Rent/Housing", 
    "Transportation", "Family Support", "Medical/Health", "Education", 
    "Entertainment", "Shopping/Clothing", "Investments/Savings", "Miscellaneous"
]

# Session state
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'user_name' not in st.session_state:
    st.session_state.user_name = None
if 'is_logged_in' not in st.session_state:
    st.session_state.is_logged_in = False

# Google OAuth Functions
def get_google_login_url():
    """Generate Google OAuth URL"""
    state = hashlib.md5(str(datetime.now()).encode()).hexdigest()[:10]
    st.session_state.google_state = state
    
    google_url = f"""https://accounts.google.com/o/oauth2/v2/auth?
    client_id={GOOGLE_CLIENT_ID}&
    redirect_uri={st.secrets['streamlit_url']}/auth/callback&
    response_type=code&
    scope=openid email profile&
    state={state}"""
    return google_url

async def handle_google_callback(code, state):
    """Handle Google OAuth callback"""
    if state != st.session_state.get('google_state'):
        return None
    
    # Exchange code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": f"{st.secrets['streamlit_url']}/auth/callback",
        "grant_type": "authorization_code",
    }
    
    token_response = requests.post(token_url, data=token_data)
    token_json = token_response.json()
    
    if "access_token" not in token_json:
        return None
    
    # Get user info
    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {token_json['access_token']}"}
    user_response = requests.get(user_info_url, headers=headers)
    user_info = user_response.json()
    
    user_id = user_info.get("email")
    user_data = {
        "user_id": user_id,
        "name": user_info.get("name", "User"),
        "email": user_id,
        "picture": user_info.get("picture", "")
    }
    
    # Store user in DB
    users = client.users
    users.replace_one({"user_id": user_id}, user_data, upsert=True)
    
    st.session_state.user_id = user_id
    st.session_state.user_name = user_data["name"]
    st.session_state.is_logged_in = True
    st.rerun()
    return user_data

# Database functions (user-isolated)
def get_expenses_col(user_id):
    return client[f"{user_id}_expenses"]

def get_income_col(user_id):
    return client[f"{user_id}_income"]

def monthly_analytics(user_id, year_month):
    """Calculate monthly analytics"""
    exp_col = get_expenses_col(user_id)
    inc_col = get_income_col(user_id)
    
    # Get monthly income
    inc_doc = inc_col.find_one({"month": year_month})
    monthly_income = inc_doc["amount"] if inc_doc else 0
    
    # Get expenses
    expenses = list(exp_col.find({"date": {"$regex": year_month}}))
    df = pd.DataFrame(expenses)
    
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

# Main App
if not st.session_state.is_logged_in:
    st.title("💰 Family Expense Tracker")
    st.markdown("### Sign in with Google to start tracking your family budget")
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔐 Sign in with Google", use_container_width=True):
            st.markdown(f"[**Click here to sign in**]({get_google_login_url()})")
    
    with col2:
        st.info("""
        **✨ Features:**
        - 📊 Real-time analytics & dashboards
        - 💰 Monthly surplus & savings tracking  
        - 👨‍👩‍👧‍👦 Perfect for single earners
        - 📱 Works on mobile
        - 🔒 Google login (secure)
        """)
    
    # Handle callback
    query_params = st.query_params
    if "code" in query_params and "state" in query_params:
        code = query_params["code"][0]
        state = query_params["state"][0]
        with st.spinner("Signing you in..."):
            user_data = await handle_google_callback(code, state)
            if user_data:
                st.success(f"Welcome {user_data['name']}!")
                st.rerun()
            else:
                st.error("Login failed. Please try again.")
                st.query_params.clear()
    
    st.stop()

# Dashboard (Logged In)
st.title(f"🏠 {st.session_state.user_name}'s Family Budget Dashboard")

# Sidebar
with st.sidebar:
    st.image(st.session_state.get('user_picture', ''), width=100)
    st.header(f"👋 {st.session_state.user_name}")
    
    # Monthly Income
    st.header("💰 Monthly Income")
    col1, col2 = st.columns(2)
    with col1:
        month = st.date_input("Month", value=date(2026, 2, 1)).strftime("%Y-%m")
    with col2:
        income_amt = st.number_input("Income (₹)", value=80000.0)
    
    if st.button("💾 Save Income", use_container_width=True):
        inc_col = get_income_col(st.session_state.user_id)
        inc_col.replace_one({"month": month}, {
            "month": month, "amount": income_amt, "source": "Salary"
        }, upsert=True)
        st.success("Income saved!")
        st.rerun()
    
    # Daily Entry
    st.header("📝 Daily Entry")
    with st.form("daily_entry"):
        exp_date = st.date_input("Date", value=date.today())
        cat = st.selectbox("Category", categories)
        amount = st.number_input("Amount (₹)", min_value=0.0)
        desc = st.text_input("Description")
        is_income = st.checkbox("Income?")
        if st.form_submit_button("➕ Add", use_container_width=True):
            exp_col = get_expenses_col(st.session_state.user_id)
            exp_col.insert_one({
                "date": datetime.combine(exp_date, datetime.min.time()),
                "category": cat,
                "amount": float(amount),
                "description": desc,
                "is_income": is_income
            })
            st.success("✅ Added!")
            st.rerun()

# Main Dashboard
tab1, tab2, tab3 = st.tabs(["📊 Overview", "📈 Charts", "📋 Entries"])

with tab1:
    col1, col2, col3, col4 = st.columns(4)
    analytics = monthly_analytics(st.session_state.user_id, "2026-02")
    
    with col1: st.metric("Income", f"₹{analytics['monthly_income']:,.0f}")
    with col2: st.metric("Expenses", f"₹{analytics['total_expenses']:,.0f}")
    with col3: st.metric("Surplus", f"₹{analytics['surplus']:,.0f}")
    with col4: st.metric("Savings %", f"{analytics['savings_rate']:.1f}%")

with tab2:
    exp_col = get_expenses_col(st.session_state.user_id)
    pipeline = [{"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}]
    data = list(exp_col.aggregate(pipeline))
    
    if data:
        df = pd.DataFrame(data)
        fig = px.pie(df, values='total', names='_id', title="Expense Breakdown")
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    exp_col = get_expenses_col(st.session_state.user_id)
    expenses = list(exp_col.find({"date": {"$regex": "2026-02"}}).sort("date", -1).limit(50))
    if expenses:
        df_exp = pd.DataFrame(expenses)
        df_exp['date'] = pd.to_datetime(df_exp['date'])
        st.dataframe(df_exp, use_container_width=True)

# Logout
if st.sidebar.button("🚪 Logout"):
    for key in ['user_id', 'user_name', 'is_logged_in', 'user_picture']:
        del st.session_state[key]
    st.rerun()
