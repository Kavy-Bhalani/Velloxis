# Velloxis — AI Image Generation Backend (Control Plane)

High-performance, lightweight FastAPI serverless control plane engineered for **Project Velloxis**.

---

## ⚡ Architecture Principles
* **Zero Fixed Cost:** Designed for **Google Cloud Run** (`min_instances = 0`) or **Render** / **Koyeb**. Fixed server cost is ₹0 when idle.
* **Smart Control Plane:** Handles authentication (Firebase Anonymous Auth), 8-gate cost firewall, atomic credits reservation, prompt safety filtering, and AdMob SSV. Never permanently stores image blobs.
* **Database:** Connects to **Supabase PostgreSQL** for atomic ledger transactions and row-lock credit checks (`schema.sql`).
* **AI Providers:** Primary routing with automatic failover between **DeepInfra** (FLUX.1 [schnell]) and **fal.ai** (Sana / FLUX.1 [schnell]).

---

## 🛠️ Environment Variables Configuration (`.env`)

Create a `.env` file in the root of the project with the following variables:

```env
# Application Settings
ENVIRONMENT=production
PORT=8080
LOG_LEVEL=INFO

# Supabase PostgreSQL Connection String (Transaction Pooler or Session Pooler)
# Format: postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
DATABASE_URL=your_supabase_connection_string_here

# AI Provider API Keys
FAL_KEY=your_fal_ai_api_key_here
DEEPINFRA_API_KEY=your_deepinfra_api_key_here

# Firebase Security
FIREBASE_PROJECT_ID=your_firebase_project_id
DEV_BYPASS_AUTH=false
ENFORCE_APP_CHECK=false

# AdMob Server-Side Verification
ADMOB_KEY_URL=https://gstatic.com/admob/reward/verifier-keys.json

# Daily Limits & Guardrails
MAX_PROMPT_LENGTH=1000
MAX_DAILY_GENERATIONS=20
MAX_DAILY_REWARDS=10
RATE_LIMIT_PER_MINUTE=10
```

---

## 🗄️ Database Setup (Supabase)
1. In your [Supabase Dashboard](https://supabase.com), navigate to **SQL Editor**.
2. Open and execute the [`schema.sql`](./schema.sql) file.
3. This creates the `users`, `credit_accounts`, `credit_transactions`, `daily_usage`, `generations`, `reports` tables, and atomic row-locked stored procedures.

---

## 🧪 Local Testing
```bash
# Install dependencies
pip install -r requirements.txt

# Run test suite
pytest

# Start local server
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
Interactive API documentation: `http://localhost:8080/docs`

---

## 🚀 Deployment Options

### Option 1: Google Cloud Run (Recommended for ₹0 Fixed Cost)
```bash
# 1. Authenticate with GCP
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID

# 2. Deploy directly from source
gcloud run deploy velloxis-backend \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 5 \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars ENVIRONMENT=production,FIREBASE_PROJECT_ID=your_firebase_project_id \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,FAL_KEY=FAL_KEY:latest,DEEPINFRA_API_KEY=DEEPINFRA_API_KEY:latest
```

### Option 2: Render (1-Click GitHub Deploy)
1. Create a new **Web Service** on [Render](https://render.com).
2. Connect your GitHub repository `KavyBhalani/Velloxis`.
3. Choose **Docker** as runtime.
4. Add your environment variables in the **Environment** tab.
5. Click **Deploy Web Service**.
