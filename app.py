import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime
import pymongo

st.set_page_config(page_title="Family Budget", page_icon="💰", layout="wide")

# MongoDB
@st.cache_resource
def init_db():
    return pymongo.MongoClient(st.secrets["mongo_uri"])["family_budget"]

client = init_db()

categories = [
    "Food & Groceries", "Utilities", "Rent/Housing", "Transportation", 
    "Family Support", "Medical", "Education", "Entertainment", 
    "Shopping", "Savings", "Miscellaneous"
]

# ✅ NATIVE GOOGLE LOGIN
st.login("🔐 Sign in with Google", type="primary")

if st.session_state["authentication_status"] != "authenticated":
    st.stop()

# User info from Google
user_id = st.session_state["oauth_id"]  # email
user_name = st.session_state["name"]
user_picture = st.session_state["picture"]

# DB functions
def get_expenses(user_id):
    return client[f"{user_id}_expenses"]

def get_income(user_id):
    return client[f"{user_id}_income"]

def get_analytics(user_id, month="2026-02"):
    inc = get_income(user_id).find_one({"month": month})
    income = inc["amount"] if inc else 0
    
    df = pd.DataFrame(list(get_expenses(user_id).find({"date": {"$regex": month}})))
    expenses = df[~df['is_income']]['amount'].sum() if not df.empty else 0
    surplus = income - expenses
    savings_rate = (surplus / income * 100) if income > 0 else 0
    
    top_cat = df[~df['is_income']].groupby('category')['amount'].sum().idxmax() if not df.empty else "No data"
    
    return income, expenses, surplus, savings_rate, top_cat

# DASHBOARD
st.title(f"🏠 {user_name}'s Budget")

with st.sidebar:
    st.image(user_picture, width=80)
    st.caption(user_id)
    
    if st.button("🚪 Logout"):
        st.logout()
        st.rerun()
    
    # Income
    st.header("💰 Income")
    col1, col2 = st.columns(2)
    with col1: month = st.date_input("Month", value=date.today()).strftime("%Y-%m")
    with col2: income = st.number_input("₹", 80000.0)
    if st.button("Save"): 
        get_income(user_id).replace_one({"month": month}, {"month": month, "amount": income}, upsert=True)
        st.rerun()
    
    # Entry
    st.header("📝 Entry")
    with st.form("add"):
        d = st.date_input("Date")
        c = st.selectbox("Category", categories)
        a = st.number_input("Amount")
        desc = st.text_input("Desc")
        inc = st.checkbox("Income?")
        if st.form_submit_button("Add"):
            get_expenses(user_id).insert_one({
                "date": datetime.combine(d, datetime.min.time()),
                "category": c, "amount": a, "description": desc, "is_income": inc
            })
            st.rerun()

# Tabs
tab1, tab2, tab3 = st.tabs(["📊 Overview", "Charts", "Entries"])

with tab1:
    i, e, s, r, t = get_analytics(user_id)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Income", f"₹{i:,.0f}")
    col2.metric("Expenses", f"₹{e:,.0f}")
    col3.metric("Surplus", f"₹{s:,.0f}")
    col4.metric("Savings", f"{r:.1f}%")

with tab2:
    data = list(get_expenses(user_id).aggregate([{"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}]))
    if data:
        df = pd.DataFrame(data)
        fig = px.pie(df, values="total", names="_id")
        st.plotly_chart(fig)

with tab3:
    ex = list(get_expenses(user_id).find().sort("date", -1).limit(20))
    if ex:
        df = pd.DataFrame(ex)
        df['date']
