# Deploy License Server to Render — Step by Step

## Files in This Directory
- `server.py` — License server (FastAPI + SQLite)
- `requirements.txt` — Python dependencies
- `render.yaml` — Render deployment config

## Step 1: Create a GitHub Repo
1. Go to https://github.com and create a new repo called `email-finder-license`
2. Make it public
3. Upload these 3 files (server.py, requirements.txt, render.yaml)

## Step 2: Deploy on Render
1. Go to https://render.com and sign in
2. Click "New" → "Web Service"
3. Connect your GitHub repo: `email-finder-license`
4. Set these settings:
   - **Name**: `email-finder-license`
   - **Environment**: `Python 3`
   - **Region**: `Oregon` (free tier)
   - **Plan**: `Free`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`
5. Click "Create Web Service"

## Step 3: Get Your URL
After deploying, your server will be at:
`https://email-finder-license.onrender.com`

## Step 4: Set Your Admin Key
Edit `server.py` line 120:
```python
ADMIN_KEY = "your-secure-random-string-here"
```

## Step 5: Create Marc's License
Go to your server URL and call:
```
POST https://email-finder-license.onrender.com/api/license/add
{
  "company": "Break Coffee of Raleigh-Durham",
  "days": 365,
  "admin_key": "YOUR_ADMIN_KEY"
}
```

This returns a license key like `EF-XXXX-XXXX-XXXX`.

## Step 6: Send to Marc
Give Marc:
1. `EmailFinder_ForMarc.zip` (already built)
2. The license key from Step 5

## Admin Commands

### View all licenses:
```
GET https://email-finder-license.onrender.com/api/license/list?admin_key=YOUR_ADMIN_KEY
```

### Deactivate Marc's license:
```
POST https://email-finder-license.onrender.com/api/license/deactivate
{
  "key": "EF-XXXX",
  "admin_key": "YOUR_ADMIN_KEY"
}
```

### Delete Marc's license:
```
POST https://email-finder-license.onrender.com/api/license/delete
{
  "key": "EF-XXXX",
  "admin_key": "YOUR_ADMIN_KEY"
}
```

### Create new license:
```
POST https://email-finder-license.onrender.com/api/license/add
{
  "company": "Break Coffee",
  "days": 365,
  "admin_key": "YOUR_ADMIN_KEY"
}
```

## How It Works When Marc Runs It
1. Marc extracts `EmailFinder_ForMarc.zip`
2. Double-clicks `EmailFinder_Launcher.exe`
3. Launcher checks license with your server
4. If active → starts Email Finder dashboard
5. If inactive → shows error message and exits

## To Shut Off
Just call the deactivate endpoint. Marc gets an error on next launch.
