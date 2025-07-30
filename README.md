# SensAI 🤖

SensAI is an intelligent language tutor bot designed for Discord. It uses Google's Gemini AI to provide real-time corrections and detailed explanations for Japanese sentences, helping users improve their grammar and phrasing in a supportive, interactive environment.

## ✨ Features

* **Real-time Corrections:** Get instant feedback on your Japanese sentences.
* **Detailed Explanations:** Understand *why* a sentence was incorrect with clear grammar points.
* **AI-Powered:** Utilizes Google's powerful Gemini model for high-quality analysis.
* **Platform Support:** Works on Discord and can be adjusted for other platforms.
* **Focused Practice:** Can be configured to operate only in specific channels to keep learning organized.

## 🚀 Getting Started

Follow these steps to set up and run your own instance of SensAI.

### Prerequisites

* Python 3.10+
* A Discord Server
* A Google Cloud account for your Gemini API key

### 1. Clone the Repository

```bash
git clone [https://github.com/your-username/SensAI.git](https://github.com/your-username/SensAI.git)
cd SensAI
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a file named `.env` in the root of the project

Now, open the `.env` file and fill in your secret keys. You only need to fill in the sections for the platform(s) you intend to use.

```ini
# --- REQUIRED FOR BOTH BOTS ---
GEMINI_API_KEY=your_gemini_api_key_here

# --- DISCORD BOT SETTINGS ---
DISCORD_TOKEN=your_discord_bot_token_here
ALLOWED_CHANNEL_ID=your_discord_channel_id_here
```

### 4. Run the Bot Locally

To run the Discord bot:
```bash
python discord_bot.py
```

## ☁️ Deployment

This bot is designed to be deployed on a service like **Render** for 24/7 uptime.

1.  Push your project to a private GitHub repository.
2.  Create a new application on Render.
3.  Set the environment variables in the Render UI instead of using a `.env` file.

* **For the Discord Bot:** Deploy as a **Web Service** (Free Tier). The `keep_alive` web server is included in `discord_bot.py`. Use a service like UptimeRobot to ping the provided URL every 5 minutes.

## 💬 Usage

* **On Discord:** In the designated channel, type `!check [your Japanese sentence]`.
    > `!check 私の猫は可愛いあります。`


## 📄 License

This project is licensed under the MIT License.
