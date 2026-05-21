# 🎀 Cinderella PVC Bot
**PDF · Video · Caption Bot**

A Telegram bot that re-captions bulk videos and PDFs with a beautiful **cc1-style caption** (Team★Toxic format).  
Works **ONLY in group chats**. Bot must be **Admin** with full rights.

---

## ✨ Features

| Command | Where | Description |
|---|---|---|
| `/start` | Group / PM | Welcome message with feature list & buttons |
| `/changecaption` | Group only | Re-caption up to **5000 videos** in sequence |
| `/changepcaption` | Group only | Re-caption up to **5000 PDFs** in sequence |
| `/setbatch` | Group only | Set global **Batch Name** for captions |
| `/setcredit` | Group only | Set global **Credit Name** for captions |
| `/viewsettings` | Group only | View current global settings |
| `/broadcast` | PM (Owner) | Broadcast to all users/groups |
| `/broadusers` | PM (Owner) | View all registered users/groups |

---

## 🎯 Caption Format (cc1 style)

**Video:**
```
📹 VID_ID: 001.

📝 Title: <video_title> .mp4

📚 Batch Name: <batch_name>

📥 Extracted By♠ : <credit_name>

➽━━━⊱∘₊𝙏𝙚𝙖𝙢★𝙏𝙤𝙭𝙞𝙘₊∘⊰━━━❥
```

**PDF:**
```
💾 PDF_ID: 001.

📝 Title: <pdf_title> .pdf

📚 Batch Name: <batch_name>

📥 Extracted By♠ : <credit_name>

➽━━━⊱∘₊𝙏𝙚𝙖𝙢★𝙏𝙤𝙭𝙞𝙘₊∘⊰━━━❥
```

---

## 🚀 Deploy on Render (Free)

1. Fork / push this repo to GitHub  
2. Create a **New Web Service** on [render.com](https://render.com)  
3. Set **Environment** → Docker  
4. Set env vars:

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Your Telegram Bot Token |
| `API_ID` | Telegram API ID |
| `API_HASH` | Telegram API Hash |
| `OWNER` | Your Telegram User ID |
| `CREDIT` | Default credit string |
| `AUTH_USERS` | Comma-separated authorized user IDs |
| `PORT` | `8000` |

5. Deploy! Flask runs on port 8000 (keeps Render service alive).

---

## ⚙️ How it works

- Bot collects forwarded videos/PDFs (deletes each after saving)
- Shows live count: `X/45 received`
- At 45 or when user sends `/Done` → re-uploads all files with cc1 caption
- Title extracted from: file name → caption `Title:` field
- Batch name & credit from **global settings** (persistent across restarts)

---

Made with ❤️ by **Team★Toxic** | [@CinderellaContactBot](https://t.me/CinderellaContactBot)
