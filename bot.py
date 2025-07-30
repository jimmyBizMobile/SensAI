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
ALLOWED_CHANNEL_ID = int(os.getenv('ALLOWED_CHANNEL_ID'))
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
You are a friendly and expert Japanese language teacher named SensAI. A student has submitted a Japanese sentence for review. Your task is to provide clear, helpful feedback in English to help them learn.

**IMPORTANT RULES:**
1.  **Your entire response MUST be in English.**
2.  When you write any Japanese text (words, phrases, or full sentences), you **MUST** follow it immediately with its romaji in parentheses. For example: `猫 (*neko*)`, `「部屋の電気がついている」 (*Heya no denki ga tsuite iru*)`, or the grammar point `「〜はずだ」 (*-hazu da*)`.

The student's sentence is:
`{user_sentence}`

Please structure your response in English using the following format:

### Initial Evaluation
Start with a friendly English greeting. Briefly state if the sentence is grammatically perfect, correct but unnatural, or has errors.

### Corrected Sentence
If the original sentence is unnatural or incorrect, provide the corrected, more natural version.
* **Corrected:** `「...」` (*...romaji...*)

### Detailed Explanation
Explain the grammar points in simple, easy-to-understand English.
* Break down the explanation using bullet points.
* Clearly explain the difference in nuance between the user's original phrasing and the corrected version.
* Maintain an encouraging tone.

### Example Sentences
Provide one or two new example sentences that use the corrected grammar point correctly. For each example, provide the Japanese, the romaji, and an English translation.
* **Example 1:** `「...」` (*...romaji...*)
    * (English translation)
* **Example 2:** `「...」` (*...romaji...*)
    * (English translation)

End with a final encouraging message. Format the entire response using clear markdown.
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