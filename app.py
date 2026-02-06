import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime
import pymongo
import plotly.graph_objects as go

# ✅ PERFECT Google Auth Library
from streamlit_google_auth import Authenticate

# Config
st.set_page_config(
    page_title="Family Budget Tracker", 
    page_icon="💰", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# MongoDB Connection (cached)
@st.cache_resource
def init_db():
    client = pymongo.MongoClient(st.secrets["mongo_uri"])
    return client["family_budget"]

client = init_db()

# Categories (India family-focused)
categories = [
    "Food & Groceries", "Utilities (Electricity, Water, Gas)", "Rent/Housing", 
    "Transportation", "Family Support", "Medical/Health", "Education", 
    "Entertainment", "Shopping/Clothing", "Investments/Savings", "Miscellaneous"
]

# ✅ GOOGLE AUTH - 6 LINES TOTAL
authenticator = Authenticate(
    client_id=st.secrets["google_client_id"],
    client_secret=st.secrets["google_client_secret"],
    cookie_name="expense_tracker",
    cookie_key="change-this-super-secret-key-2026-in-production",
    redirect_uri=st.secrets["streamlit_url"],
    cookie_expiry_days=30
)

# Perfect login button
authenticator.login("🔐 **Sign in with Google**", "primary", key="google_login")

# Stop if not authenticated
if st.session_state["authentication_status"] != "authenticated":
    st.stop()

# ✅ Get user info (automatic from Google)
try:
    user_id = st.session_state["username"]  # Google email
    user_name = st.session_state["name"]
    user_picture = st.session_state["picture"]
    st.session_state.user_id = user_id
    st.session_state.user_name = user_name
    st.session_state.user_picture = user_picture
except:
    user_id = "user@gmail.com"
    user_name = "User"
    user_picture = None

# Database functions (user-isolated)
def get_expenses_col(user_id):
    return client[f"{user_id}_expenses"]

def get_income_col(user_id):
    return client[f"{user_id}_income"]

def monthly_analytics(user_id, year_month):
    """Calculate surplus, savings rate, etc."""
    exp_col = get_expenses_col(user_id)
    inc_col = get_income_col(user_id)
    
    # Monthly income
    inc_doc = inc_col.find_one({"month": year_month})
    monthly_income = inc_doc["amount"] if inc_doc else 0
    
    # Expenses
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

# DASHBOARD
st.title(f"🏠 {user_name}'s Family Budget Dashboard")

# Sidebar with user info + logout
with st.sidebar:
    if user_picture:
        st.image(user_picture, width=100, caption=user_id)
    st.header(f"👋 {user_name}")
    
    # Logout button
    if st.button("🚪 Logout", use_container_width=True):
        authenticator.logout()
        st.cache_resource.clear()
        st.rerun()
    
    # Monthly Income Setup
    st.header("💰 Monthly Income")
    col1, col2 = st.columns(2)
    with col1:
        month = st.date_input("Month", value=date(2026, 2, 1)).strftime("%Y-%m")
    with col2:
        income_amt = st.number_input("Income (₹)", value=80000.0, min_value=0.0)
    
    if st.button("💾 Save Income", use_container_width=True):
        inc_col = get_income_col(user_id)
        inc_col.replace_one({"month": month}, {
            "month": month, "amount": income_amt, "source": "Salary"
        }, upsert=True)
        st.success("✅ Income saved!")
        st.rerun()
    
    # Daily Expense Entry
    st.header("📝 Daily Entry")
    with st.form("daily_entry"):
        exp_date = st.date_input("Date", value=date.today())
        cat = st.selectbox("Category", categories)
        amount = st.number_input("Amount (₹)", min_value=0.0)
        desc = st.text_input("Description")
        is_income = st.checkbox("Income?")
        if st.form_submit_button("➕ Add Entry", use_container_width=True):
            exp_col = get_expenses_col(user_id)
            exp_col.insert_one({
                "date": datetime.combine(exp_date, datetime.min.time()),
                "category": cat,
                "amount": float(amount),
                "description": desc,
                "is_income": is_income
            })
            st.success("✅ Entry added!")
            st.rerun()

# Main Dashboard Tabs
tab1, tab2, tab3 = st.tabs(["📊 Overview", "📈 Charts", "📋 Recent Entries"])

with tab1:
    col1, col2, col3, col4 = st.columns(4)
    analytics = monthly_analytics(user_id, "2026-02")
    
    with col1:
        st.metric("Income", f"₹{analytics['monthly_income']:,.0f}")
    with col2:
        st.metric("Expenses", f"₹{analytics['total_expenses']:,.0f}")
    with col3:
        st.metric("Surplus", f"₹{analytics['surplus']:,.0f}")
    with col4:
        st.metric("Savings %", f"{analytics['savings_rate']:.1f}%")

with tab2:
    exp_col = get_expenses_col(user_id)
    pipeline = [{"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}]
    data = list(exp_col.aggregate(pipeline))
    
    if data:
        df = pd.DataFrame(data)
        fig = px.pie(df, values='total', names='_id', title="Expense Breakdown by Category")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("👆 Add some expenses to see charts!")

with tab3:
    exp_col = get_expenses_col(user_id)
    expenses = list(exp_col.find({"date": {"$regex": "2026-02"}}).sort("date", -1).limit(50))
    if expenses:
        df_exp = pd.DataFrame(expenses)
        if 'date' in df_exp.columns:
            df_exp['date'] = pd.to_datetime(df_exp['date'])
        st.dataframe(df_exp, use_container_width=True)
    else:
        st.info("👆 Start adding daily expenses!")

st.markdown("---")
st.caption("💰 Family Budget Tracker | Built for single earners | Deployed on Streamlit Cloud")
