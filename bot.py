import discord
from discord.ext import commands, tasks
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

# --- BOT SETTINGS ---
ALLOWED_CHANNEL_ID = int(os.getenv('ALLOWED_CHANNEL_ID'))
QUIZ_CHANNEL_ID = int(os.getenv("QUIZ_CHANNEL_ID"))

MAX_INPUT_LENGTH = 500 # Max characters for user's sentence
MAX_RETRIES = 3
RETRY_DELAY = 2 # Seconds to wait between retries


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
Generate a single quiz question based on a common Japanese grammar point or vocabulary word **specifically from the N3 curriculum**.

**IMPORTANT:** Your response MUST be a single line in the following format, using a pipe "|" as a separator:
Question Text|Correct Answer|Brief Explanation of the tested point

**Example Formats:**
* Fill in the blank: 「健康のため、毎日運動する＿＿＿しています。」 (Making an effort)|ように|The「〜ようにしています」grammar is used to express making a continuous effort to do something.
* Translate this sentence to natural Japanese: "It seems the meeting has already started."|会議はもう始まったようです。|The「〜ようです」grammar is used to make a judgment based on sensory information.
* What is the correct form of the verb?: "This PC is easy to use." (使う)|このパソコンは使いやすいです。|The「〜やすい」grammar is attached to a verb stem to mean "easy to do".
"""

QUIZ_GRADING_PROMPT = """
You are a friendly Japanese teacher, SensAI. A student was given a quiz question and has provided an answer. Your task is to grade it.

**The Original Question was:** "{question}"
**The Correct Answer is:** "{correct_answer}"
**The Student's Answer is:** "{user_answer}"

**Your Task:**
1.  Your entire response MUST be in English.
2.  When you write any Japanese text, you MUST follow it with its romaji in parentheses.
3.  **Critically re-evaluate the question.** If the student's answer is also a grammatically correct and natural fit for the blank (even if it's not the one you originally intended), you MUST acknowledge it as a valid alternative before explaining your intended N3-level answer.
4.  Start by stating if the student's answer is "Correct!", "Also correct!", "Close, but not quite.", or "Incorrect."
5.  Provide a clear, kind, and simple explanation of why the answer is right or wrong, comparing it to the correct answer.
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

    # --- Retry Logic Starts Here ---
    for attempt in range(MAX_RETRIES):
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, gemini_model.generate_content, QUIZ_GENERATION_PROMPT)
            
            question, answer, explanation = response.text.strip().split('|')

            current_quiz = { "question": question, "answer": answer, "explanation": explanation }

            await channel.send(f"🧠 **New Japanese Quiz!**\n\n> {question}\n\nType your answer in the chat to respond!")
            print(f"Posted new quiz successfully. Answer: {answer}")
            
            # On success, exit the function immediately.
            return

        except Exception as e:
            print(f"Quiz generation attempt {attempt + 1} of {MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:  # If this wasn't the last attempt
                await asyncio.sleep(RETRY_DELAY) # Wait before retrying
            else: # This was the last attempt, and all have failed.
                print("All attempts to generate a quiz question failed. The task will try again in the next cycle.")

# --- BOT EVENTS AND COMMANDS ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    if not post_quiz_question.is_running():
        post_quiz_question.start()

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
                user_answer=user_answer
            )

            for attempt in range(MAX_RETRIES):
                try:
                    loop = asyncio.get_running_loop()
                    response = await loop.run_in_executor(None, gemini_model.generate_content, grading_prompt)
                    await message.reply(response.text)
                    current_quiz = {}
                    print("Quiz graded and reset successfully.")
                    break
                except Exception as e:
                    print(f"Attempt {attempt + 1} of {MAX_RETRIES} failed: {e}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        await message.reply("Sorry, I had trouble grading your answer due to a temporary issue. **Please feel free to submit your answer again!**")
        return

    # --- Logic for the Commands Channel ---
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