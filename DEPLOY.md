# Deployment Guide (Render)

This project is configured for easy deployment on **Render.com**.

## Prerequisites
- A Render account.
- This repository pushed to GitHub/GitLab.
- Your API Keys ready:
  - `GROQ_API_KEY`
  - `DEEPGRAM_API_KEY`
  - `MONGO_URI`
  - `TELEGRAM_TOKEN`
  - `TELEGRAM_CHAT_ID`

## Deployment Steps

1.  **Log in to Render** and go to your Dashboard.
2.  Click **New +** -> **Blueprint**.
3.  Connect your GitHub repository.
4.  Render will detect the `render.yaml` file.
5.  **Fill in the Environment Variables** when prompted:
    -   `GROQ_API_KEY`: Your key from Groq console.
    -   `DEEPGRAM_API_KEY`: Your key from Deepgram.
    -   `MONGO_URI`: Your MongoDB connection string.
    -   `TELEGRAM_TOKEN`: Your Telegram bot token.
    -   `TELEGRAM_CHAT_ID`: Your Telegram chat ID.
6.  Click **Apply**.
7.  Wait for the implementation to complete. You will see 3 services created:
    -   `asta-backend` (Web Service)
    -   `asta-worker` (Background Worker)
    -   `asta-frontend` (Static Site)

### Post-Deployment Configuration (IMPORTANT)

The frontend needs to know where the backend is located to send API requests.
This cannot be fully automated during the *initial* creation because the backend URL is generated dynamically.

1.  Once the `asta-backend` service is live, **copy its URL** (e.g., `https://asta-backend-xyz.onrender.com`).
2.  Go to the **`asta-frontend`** service in your Render Dashboard.
3.  Go to **Environment**.
4.  Add a new Environment Variable:
    -   **Key**: `VITE_API_URL`
    -   **Value**: The backend URL you copied (e.g., `https://asta-backend-xyz.onrender.com`).
5.  **Save Changes**. This will trigger a re-deploy of the frontend.
6.  Once finished, visit your frontend URL!

## Troubleshooting

-   **Frontend 404s on API calls**: Check the Network tab. If requests go to `https://asta-frontend.../api/...`, you forgot to set `VITE_API_URL`. They should go to `https://asta-backend.../api/...`.
-   **Backend Crashes**: Check the Logs tab for `asta-backend`. Usually missing env vars.
-   **Worker Idle**: The worker logs might show "Polling..." but process nothing if MongoDB connectivity fails. Ensure IP Whitelist on MongoDB Atlas includes `0.0.0.0/0` (allow all) or Render's IPs.
