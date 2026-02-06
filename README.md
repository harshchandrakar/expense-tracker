# Family Expense Tracker - Google OAuth

## 🚀 Quick Start

1. **Google OAuth Setup** (5 mins):
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create project → APIs & Services → Credentials
   - Create OAuth 2.0 Client ID (Web application)
   - Authorized redirect URIs: `http://localhost:8000/auth/google/callback`
   - Copy Client ID & Secret to `.env`

2. **MongoDB Atlas**:
   - Create free cluster
   - Get connection string → Add to `.env`

3. **Run**:
```bash
pip install -r requirements.txt
uvicorn main:app --reload  # Backend: http://localhost:8000
streamlit run app.py       # Frontend: http://localhost:8501
