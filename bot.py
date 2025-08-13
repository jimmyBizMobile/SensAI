import discord
from discord.ext import commands, tasks
import os
import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
import asyncio

from sqlalchemy import String, Text, func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# --- DATABASE MODEL SETUP ---
class Base(DeclarativeBase):
    pass

class QuizHistory(Base):
    __tablename__ = "quiz_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    grammar_point: Mapped[str] = mapped_column(String(255))
    question_text: Mapped[str] = mapped_column(Text)
    correct_answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    asked_at: Mapped[str] = mapped_column(
        Text, 
        server_default=func.now(), 
        default=None
    )

# --- CONFIGURATION ---
# Load .env file for local testing
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# --- BOT SETTINGS ---
ALLOWED_CHANNEL_ID = int(os.getenv('ALLOWED_CHANNEL_ID'))
QUIZ_CHANNEL_ID = int(os.getenv("QUIZ_CHANNEL_ID"))

MAX_INPUT_LENGTH = 500 # Max characters for user's sentence
MAX_RETRIES = 3
RETRY_DELAY = 2 # Seconds to wait between retries

HISTORY_COUNT = 30
# Get the database URL from your environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")

# Create the async engine and session factory
engine = create_async_engine(DATABASE_URL)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

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

QUIZ_GENERATION_PROMPT = """
You are a Japanese language teacher creating a quiz question for a student studying for the **JLPT N3 level**.
Generate a single, new quiz question based on a common Japanese grammar point or vocabulary word **specifically from the N3 curriculum**.

**Avoid generating a question related to any of the following topics, as they have been asked recently:**
{history}

**IMPORTANT:** Your response MUST be a single line in the following format, with FIVE parts separated by a pipe "|":
Question Text|Question Reading with Furigana|Correct Answer|Specific Grammar Point Tested|Brief Explanation

**"Question Reading with Furigana"** should show the hiragana reading for all kanji, using the format `漢字(かんじ)`.

**The "Specific Grammar Point Tested"** should be a short, identifiable key (e.g., "〜ようにする", "〜ようです", "〜やすい", "〜べき").

**Example Formats:**
* 「健康のため、毎日運動する＿＿＿しています。」|「健康(けんこう)のため、毎日(まいにち)運動(うんどう)する＿＿＿しています。」|ように|〜ようにする|The「〜ようにしています」grammar is used to express making a continuous effort to do something.
* "It seems the meeting has already started."|「会議(かいぎ)はもう始(はじ)まったようです。」|会議はもう始まったようです。|〜ようです|The「〜ようです」grammar is used to make a judgment based on sensory information.
* "This PC is easy to use." (使う)|「このパソコンは使(つか)いやすいです。」|このパソコンは使いやすいです。|〜やすい|The「〜やすい」grammar is attached to a verb stem to mean "easy to do".
"""

QUIZ_GRADING_PROMPT = """
You are a friendly Japanese teacher, SensAI. A student was given a quiz question and has provided an answer. Your task is to grade it.

**The Original Question was:** "{question}"
**The Correct Answer is:** "{correct_answer}"
**The N3 Grammar Point Tested was:** "{grammar_point}"
**The Student's Answer is:** "{user_answer}"

**Your Task:**
1.  Your entire response MUST be in English.
2.  When you write any Japanese text, you MUST follow it with its romaji in parentheses.
3.  **Critically re-evaluate the question.** If the student's answer is also a grammatically correct and natural fit for the blank (even if it's not the one you originally intended), you MUST acknowledge it as a valid alternative before explaining your intended N3-level answer.
4.  Start by stating if the student's answer is "Correct!", "Also correct!", "Close, but not quite.", or "Incorrect."
5.  Provide a clear, kind, and simple explanation of why the answer is right or wrong, focusing on the intended grammar point: **{grammar_point}**.
6.  End with an encouraging message.
Format the response using Discord markdown.
"""

# --- QUIZ STATE MANAGEMENT ---
current_quiz = {}

# --- TIMED QUIZ TASK ---
@tasks.loop(hours=2)
async def post_quiz_question():
    global current_quiz
    channel = bot.get_channel(QUIZ_CHANNEL_ID)
    if not channel:
        print(f"Error: Quiz channel with ID {QUIZ_CHANNEL_ID} not found.")
        return

    # Fetch Recent History using SQLAlchemy
    recent_topics = "None"
    try:
        async with async_session_factory() as session:
            stmt = (
                select(QuizHistory.grammar_point)
                .order_by(QuizHistory.asked_at.desc())
                .limit(HISTORY_COUNT)
            )
            result = await session.execute(stmt)
            history_list = result.scalars().all()
            if history_list:
                recent_topics = ", ".join(history_list)
    except Exception as e:
        print(f"Error fetching quiz history via SQLAlchemy: {e}")

    # Generation Logic with Retry
    for attempt in range(MAX_RETRIES):
        try:
            prompt = QUIZ_GENERATION_PROMPT.format(history=recent_topics)
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, gemini_model.generate_content, prompt)
            
            question, reading, answer, grammar_point, explanation = map(str.strip, response.text.split('|'))


            # Create a Python object for the new quiz
            new_quiz_entry = QuizHistory(
                grammar_point=grammar_point,
                question_text=question,
                correct_answer=answer,
                explanation=explanation
            )

            # Add the new object to the database
            async with async_session_factory() as session:
                session.add(new_quiz_entry)
                await session.commit()

            current_quiz = {
                "question": question,
                "reading": reading, # New field
                "answer": answer,
                "grammar_point": grammar_point,
                "explanation": explanation
            }
            await channel.send(f"🧠 **New Japanese Quiz!**\n\n> {question}\n> {reading}\n\nType your answer in the chat to respond!")
            print(f"Posted & saved new quiz. Grammar Point: {grammar_point}")
            
            return # Success!

        except Exception as e:
            print(f"Quiz generation attempt {attempt + 1} of {MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
            else:
                print("All quiz generation attempts failed. Will try again in the next cycle.")

# --- BOT EVENTS AND COMMANDS ---
@bot.event
async def on_ready():
    # Your original login message is perfectly fine
    print(f'Logged in as {bot.user.name}')
    # This new check is critical. The task will fail without the database URL.
    if not DATABASE_URL:
        print("CRITICAL: DATABASE_URL is not set. Quiz task cannot start.")
        return
    # Your original check is good practice to prevent starting the task multiple times.
    if not post_quiz_question.is_running():
        post_quiz_question.start()
        print("Quiz task has been started.")

@bot.event
async def on_command_error(ctx, error):
    """A global error handler for all commands."""
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"This command is on cooldown. Please try again in {error.retry_after:.1f} seconds.", delete_after=5)
    elif isinstance(error, commands.CommandInvokeError):
        print(f"In {ctx.command.name}: {error.original}")
        await ctx.send("An unexpected error occurred while running this command.")
    else:
        print(f"An unhandled error occurred: {error}")

@bot.event
async def on_message(message):
    global current_quiz
    if message.author == bot.user:
        return

    # --- Logic for the Quiz Channel ---
    if message.channel.id == QUIZ_CHANNEL_ID:
        if current_quiz and not message.content.startswith('!'):
            user_answer = message.content
            await message.add_reaction('✅')
            
            grading_prompt = QUIZ_GRADING_PROMPT.format(
                question=current_quiz['question'],
                correct_answer=current_quiz['answer'],
                grammar_point=current_quiz['grammar_point'], # This line is new
                user_answer=user_answer
            )

            for attempt in range(MAX_RETRIES):
                try:
                    loop = asyncio.get_running_loop()
                    response = await loop.run_in_executor(None, gemini_model.generate_content, grading_prompt)
                    await message.reply(response.text)
                    current_quiz = {} # Reset the quiz after grading
                    print("Quiz graded and reset successfully.")
                    break
                except Exception as e:
                    print(f"Grading attempt {attempt + 1} of {MAX_RETRIES} failed: {e}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        await message.reply("Sorry, I had trouble grading your answer due to a temporary issue. Please feel free to submit your answer again!")
        return

    # --- Logic for other channels (if any) ---
    if message.channel.id == ALLOWED_CHANNEL_ID:
        await bot.process_commands(message)
        return

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
            raise e

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
            raise e

# --- START THE BOT ---
async def main():
    """The main entry point for starting the bot."""
    if not DISCORD_TOKEN:
        print("CRITICAL: DISCORD_TOKEN is not set. The bot cannot start.")
        return
        
    # Start the keep-alive server in a separate thread.
    keep_alive()
    
    # Use an async context manager to handle the bot's lifecycle.
    # This is more robust than a simple bot.run() call.
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        # This is the modern, recommended way to run an asyncio program.
        asyncio.run(main())
    except discord.errors.LoginFailure:
        print("Login failed: Improper token has been passed.")
    except KeyboardInterrupt:
        print("Bot is shutting down.")