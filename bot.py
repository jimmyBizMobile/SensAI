import discord
from discord.ext import commands
import os
import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
import asyncio

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

GRAMMAR_EXPLANATION_PROMPT = """
You are a clear and concise Japanese language expert named SensAI. Your task is to explain a specific Japanese grammar point to an English-speaking learner.

**IMPORTANT RULES:**
1.  **Your entire response MUST be in English.**
2.  When you write any Japanese text, you **MUST** follow it immediately with its romaji in parentheses. For example: `猫 (neko)`.

The grammar point to explain is:
`{grammar_point}`

Please structure your response in English using the following format:

### [Grammar Point] (romaji)
Provide a title with the grammar point itself and its romaji.

**Meaning / Usage:**
Explain what the grammar point means and when it is used in simple terms.

**Formation:**
Clearly show how to construct the grammar point (e.g., Verb (Dictionary Form) + ように).

**Variations (e.g., Negative Form):**
Explain other common forms or variations of the grammar point, such as its negative form or past tense, showing how they are constructed.

**Example Sentences:**
Provide at least two clear example sentences, each with Japanese, romaji, and an English translation. Use examples that showcase different variations if possible.

**Nuance / Comparison:**
If applicable, compare the grammar point to a similar one to clarify the difference in nuance (e.g., for 「ように」, briefly compare it to 「ために」).

Format the entire response using clear markdown and end with an encouraging sentence.
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
            # Get the current asyncio event loop
            loop = asyncio.get_running_loop()
            full_prompt = JAPANESE_TUTOR_PROMPT.format(user_sentence=sentence)

            # Run the synchronous Gemini call in a separate thread
            response = await loop.run_in_executor(
                None,  # Use the default thread pool executor
                gemini_model.generate_content,  # The blocking function to run
                full_prompt  # The argument to pass to the function
            )
            
            feedback = response.text

            # 3. Split the response if it's over 2000 characters
            for i in range(0, len(feedback), 2000):
                await ctx.send(feedback[i:i + 2000])
        except Exception as e:
            print(f"An error occurred: {e}")
            await ctx.send("Sorry, something went wrong. Please try again later.")

@bot.command(name='grammar')
async def explain_grammar(ctx, *, grammar_point: str):
    """Explains a Japanese grammar point using Gemini."""
    # 1. Check if the command is used in the allowed channel
    if ctx.channel.id != ALLOWED_CHANNEL_ID:
        await ctx.send(f"Please use this command in the <#{ALLOWED_CHANNEL_ID}> channel.", delete_after=10)
        return

    # 2. Check if the user's input is too long
    if len(grammar_point) > 50: # Shorter limit for grammar points
        await ctx.send("That grammar point seems a bit long. Please provide a more concise term.")
        return

    async with ctx.typing():
        try:
            # Get the current asyncio event loop
            loop = asyncio.get_running_loop()
            full_prompt = GRAMMAR_EXPLANATION_PROMPT.format(grammar_point=grammar_point)

            # Run the synchronous Gemini call in a separate thread
            response = await loop.run_in_executor(
                None,  # Use the default thread pool executor
                gemini_model.generate_content,  # The blocking function to run
                full_prompt  # The argument to pass to the function
            )
            
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