import discord
from discord.ext import commands
import os
import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# --- CONFIGURATION ---
# Load .env file for local testing
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# --- BOT SETTINGS (EDIT THESE) ---
ALLOWED_CHANNEL_ID = os.getenv('ALLOWED_CHANNEL_ID')
MAX_INPUT_LENGTH = 500 # Max characters for user's sentence

# Configure Gemini API and Discord bot intents
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-pro')
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- KEEP-ALIVE WEB SERVER FOR RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Gemini-sensei is awake!"

def run_flask_app():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    server_thread = Thread(target=run_flask_app)
    server_thread.start()

# --- PROMPT TEMPLATE ---
JAPANESE_TUTOR_PROMPT = """
You are a friendly, encouraging, and expert Japanese language teacher named "Gemini-sensei" (ジェミニ先生). A student has submitted a Japanese sentence for you to review. Your task is to provide feedback that is helpful for their learning process. The current time is Tuesday, 12:12 PM JST in Shinjuku, Tokyo.

The student's sentence is:
`{user_sentence}`

Please structure your response according to these rules:
1.  **Initial Evaluation:** Start by stating whether the sentence is perfectly natural, grammatically correct but unnatural, or contains errors.
2.  **Correction (if needed):** Provide the most natural, corrected version. Present it clearly like this:
    * **Corrected Sentence (修正後):** `「...」`
3.  **Detailed Explanation (詳しい説明):** Explain *why* the original sentence was incorrect. Break down the errors one by one.
4.  **Example Sentence (例文):** Provide one or two additional examples to reinforce the lesson.
5.  **Tone:** Maintain a positive and supportive tone.

Format your entire response using Discord markdown.
"""

# --- BOT EVENTS AND COMMANDS ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command(name='check')
async def check_japanese_sentence(ctx, *, sentence: str):
    """Checks a Japanese sentence using Gemini."""
    # 1. Check if the command is used in the allowed channel
    if ctx.channel.id != ALLOWED_CHANNEL_ID:
        await ctx.send(f"Please use this command in the <#{ALLOWED_CHANNEL_ID}> channel.", delete_after=10)
        return

    # 2. Check if the user's sentence is too long
    if len(sentence) > MAX_INPUT_LENGTH:
        await ctx.send(f"Your sentence is too long! Please keep it under {MAX_INPUT_LENGTH} characters.")
        return

    async with ctx.typing():
        try:
            full_prompt = JAPANESE_TUTOR_PROMPT.format(user_sentence=sentence)
            response = gemini_model.generate_content(full_prompt)
            feedback = response.text

            # 3. Split the response if it's over 2000 characters
            for i in range(0, len(feedback), 2000):
                await ctx.send(feedback[i:i + 2000])
        except Exception as e:
            print(f"An error occurred: {e}")
            await ctx.send("Sorry, something went wrong. Please try again later.")

# --- START THE BOT ---
keep_alive()
bot.run(DISCORD_TOKEN)