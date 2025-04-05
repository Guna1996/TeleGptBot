import asyncio
import os
import re
import google.generativeai as genai
import requests
import speech_recognition as sr
from typing import Final
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from gtts import gTTS
from datetime import timedelta
from pydub import AudioSegment

# Bot configuration
TOKEN: Final = '1707467959:AAEVhQeYzTAlDvN_TimqMa6TFYIuZ_hy9oE'
BOT_USERNAME: Final = '@Lilly007_bot'

# Google Gemini configuration
API_KEY = "AIzaSyCH4cYp_chKtFsRvIMxqNrIIbpCFQXNtkI"
MODEL_NAME = "gemini-1.5-pro"

# Content moderation patterns
BAD_WORDS_PATTERNS = [
    r"\b(?:porn|xxx|sex|adult|free sex|thevidiya|baadu|punda|koothi|bitch|casino|gambling|bet|mayiru|mood|kami di|nude)\b",
    r"\b(?:ass|dick|fuck|slut|whore|nigga|cunt|faggot|twat|tranny|horny|sexy)\b",
]

LINK_PATTERNS = [
    r"https?://\S+",  # General URL pattern
    r"www\.\S+",  # URLs starting with www
    r"t\.me/\S+",  # Telegram links
    r"telegram\.(?:me|org|dog)/\S+",  # Different Telegram link formats
    r"@\w+",  # Potential Telegram handles
    r"join\.?\s*(?:my|our|the)?\s*(?:channel|group|chat)",  # Join invitations
    r"\b(?:click|visit|check out|join)\b.{0,30}\b(?:link|url|website|channel|group)\b",  # Link invitations
    r"\b(?:buy|discount|available|pay|service|free|job|girls|win|trading|invest|free|come|call|msg|message|promocode|advertise|buy now|di|dm|trade)\b"
]

# Live Score API URL
LIVE_SCORE_API_URL = "https://cric-score.skdev.one/scorecard/115068"  # Replace with the actual live score API endpoint

def is_innings1_completed(data):
    innings1 = data.get("Innings1", [{}])[2]
    if innings1 and "overs" in innings1:
        overs_played = float(innings1["overs"])
        return overs_played >= 20
    return False

def get_live_ipl_score():
    try:
        response = requests.get(LIVE_SCORE_API_URL)
        data = response.json()

        # Check if Innings1 is completed based on overs
        innings1_completed = is_innings1_completed(data)

        if innings1_completed:  # If Innings1 is completed (20 or more overs)
            innings1 = data.get("Innings2", [{}])[2]  # Get the final score of Innings1
            score_data = innings1
            opponent_team = data.get("Innings1", [{}])[2].get("team", "Opponent Team")
        else:  # If Innings1 is not completed, use Innings2
            innings2 = data.get("Innings1", [{}])[2]  # Get the final score of Innings2
            score_data = innings2
            opponent_team = data.get("Innings2", [{}])[2].get("team", "Opponent Team")

        # Extract relevant information from the chosen innings
        score = score_data.get("score", 'Score not available')
        team = score_data.get("team", 'Team not available')
        overs = score_data.get("overs", 'Overs not available')
        wickets = score_data.get("wickets", 'Wickets not available')

        # Constructing the live score message with 'vs' (opponent team)
        score_message = f"Live IPL Score:\n\n{opponent_team} vs {team} - {score} ({overs}) | Wickets: {wickets}"

        # Return a tuple (score message and match data)
        return score_message, data

    except Exception as e:
        # In case of an error, return a default message and empty data
        return "Error fetching live score: " + str(e), None

def get_live_ipl_score_single():
    try:
        response = requests.get(LIVE_SCORE_API_URL)
        data = response.json()

        # Check if Innings1 is completed or not based on overs
        innings1_completed = is_innings1_completed(data)

        if innings1_completed:  # If Innings1 is completed (20 or more overs)
            innings1 = data.get("Innings2", [{}])[2]  # Get the final score of Innings1
            score_data = innings1
            opponent_team = data.get("Innings1", [{}])[2].get("team", "Opponent Team")
            print("2222", data.get("Innings2", [{}])[2]);

        else:  # If Innings1 is not completed, use Innings2
            innings2 = data.get("Innings1", [{}])[2]  # Get the final score of Innings2
            score_data = innings2
            print("1111", data.get("Innings2", [{}])[2])
            opponent_team = data.get("Innings2", [{}])[2].get("team", "Opponent Team")

        # Extract relevant information from the chosen innings
        score = score_data.get("score", 'Score not available')
        team = score_data.get("team", 'Team not available')
        overs = score_data.get("overs", 'Overs not available')
        wickets = score_data.get("wickets", 'Wickets not available')

        # Constructing the live score message with 'vs' (opponent team)
        score_message = f"Live IPL Score:\n\n{opponent_team} vs {team} - {score} ({overs}) | Wickets: {wickets}"
        return score_message

    except Exception as e:
        return f"Error fetching live score: {str(e)}"

# Command handler for 'IPL' command
async def ipl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responds with the live IPL score when a user sends the command 'IPL'."""
    print("score")
    live_score = get_live_ipl_score_single()
    print("score", live_score)
    await update.message.reply_text(live_score)


# Initialize Google Gemini
def initialize_gemini():
    """Initialize and configure the Gemini AI model."""
    genai.configure(api_key=API_KEY)

    generation_config = {
        "temperature": 0.9,
        "top_p": 1,
        "max_output_tokens": 500,
        "response_mime_type": "text/plain",
    }

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config=generation_config,
    )

    return model.start_chat(history=[])

# Content moderation patterns
BAD_WORDS_PATTERNS = [
    r"\b(?:porn|xxx|sex|adult|free sex|thevidiya|baadu|punda|koothi|bitch|casino|gambling|bet|mayiru|mood|kami di|nude)\b",
    r"\b(?:ass|dick|fuck|slut|whore|nigga|cunt|faggot|twat|tranny|horny|sexy)\b",
]

LINK_PATTERNS = [
    r"https?://\S+",
    r"www\.\S+",
    r"t\.me/\S+",
    r"telegram\.(?:me|org|dog)/\S+",
    r"@\w+",
    r"join\.?\s*(?:my|our|the)?\s*(?:channel|group|chat)",
    r"\b(?:click|visit|check out|join)\b.{0,30}\b(?:link|url|website|channel|group)\b",
    r"\b(?:buy|discount|available|pay|service|free|job|girls|win|trading|invest|free|come|call|msg|message|promocode|advertise|buy now|di|dm|trade)\b"
]

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Hello! Thanks for chatting with me! I am Lilly!')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('I am Lilly. Please type or send a voice message, and I will assist you!')

# Content moderation
def contains_bad_words(text: str) -> bool:
    text = text.lower()
    return any(re.search(pattern, text) for pattern in BAD_WORDS_PATTERNS)

def contains_links(text: str) -> bool:
    text = text.lower()
    return any(re.search(pattern, text) for pattern in LINK_PATTERNS)

# Handle voice messages
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"update Voice Text: {update}")
    """Convert voice messages to text and process them."""
    file = await update.message.voice.get_file()
    file_path = "voice.ogg"
    await file.download_to_drive(file_path)

    # Convert to WAV format
    audio = AudioSegment.from_ogg(file_path)
    audio.export("voice.wav", format="wav")

    # Convert speech to text
    recognizer = sr.Recognizer()
    with sr.AudioFile("voice.wav") as source:
        audio_data = recognizer.record(source)

    try:
        text = recognizer.recognize_google(audio_data)
        print(f"Recognized Voice Text: {text}")

        # Process text as a normal message
        await handle_message(update, context, text)

    except sr.UnknownValueError:
        await update.message.reply_text("Sorry, I couldn't understand the audio.")
    except sr.RequestError:
        await update.message.reply_text("There was an issue processing your voice. Try again.")

    # Cleanup
    os.remove("voice.ogg")
    os.remove("voice.wav")

# Handle text messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None):
    """Process messages (text and converted voice), moderate content, and generate AI responses."""
    message_type: str = update.message.chat.type
    text = text or update.message.text
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    username = update.message.from_user.username

    print(f'User ({chat_id}) in {message_type}: "{text}"')

    # Content moderation
    if contains_bad_words(text):
        await handle_bad_words_violation(update, context, username, chat_id, user_id)
        return

    if contains_links(text):
        await handle_link_violation(update, context, username, chat_id, user_id)
        return

    # Process with AI model
    if message_type == 'supergroup':
        response = await process_group_message(update, text, chat_session)
        if not response:
            return
    else:
        response = chat_session.send_message(text).text

    print('Bot:', response)
    await send_voice_response(update, response)

async def process_group_message(update: Update, text: str, chat_session) -> str:
    """Process messages in group chats, only responding when addressed."""
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == 1707467959:
        return chat_session.send_message(text.strip()).text
    elif BOT_USERNAME in text:
        return chat_session.send_message(text.replace(BOT_USERNAME, '').strip()).text
    return None

async def handle_bad_words_violation(update, context, username, chat_id, user_id):
    """Ban users for inappropriate content."""
    await update.message.reply_text(f"@{username}, inappropriate content detected. You have been banned.")
    await context.bot.ban_chat_member(chat_id, user_id)
    await context.bot.delete_message(chat_id, update.message.message_id)

async def handle_link_violation(update, context, username, chat_id, user_id):
    """Mute users for sending links."""
    mute_duration = timedelta(days=1)
    until_date = update.message.date + mute_duration
    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False
    )
    await update.message.reply_text(f"@{username}, sharing links is not allowed. Muted for 1 day.")
    await context.bot.restrict_chat_member(chat_id, user_id, permissions=permissions, until_date=until_date)
    await context.bot.delete_message(chat_id, update.message.message_id)

async def send_voice_response(update, response):
    """Convert AI-generated text to voice and send it."""
    clean_text = response.replace("*", "")
    tts = gTTS(clean_text)
    tts.save("voice.mp3")

    with open("voice.mp3", "rb") as audio:
        await update.message.reply_voice(audio)

    os.remove("voice.mp3")

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    print(f'Update {update} caused error {context.error}')

async def send_live_score_periodically(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send live IPL score updates every 7 minutes until the match is completed."""
    chat_id = update.message.chat_id

    while True:
        # Get live score and match data
        live_score, data = get_live_ipl_score()

        if data is None:
            await context.bot.send_message(chat_id=chat_id, text="Error fetching live score. Please try again later.")
            break

        # Safely check if 'data' is not None and access its 'result' and 'winning_team' fields
        winning_team = None
        if data:
            winning_team = data.get("result", {}).get("winning_team", None)

        # If the match is not completed
        if winning_team == "Not Completed":
            # Send live score update
            await context.bot.send_message(chat_id=chat_id, text=live_score)

            # Wait for 7 minutes (420 seconds) before sending the next update
            await asyncio.sleep(300)
        else:
            # Match is completed, send the winning team and stop updates
            await context.bot.send_message(chat_id=chat_id, text=f"Match is completed! Winning team: {winning_team}")
            break

# Command handler to start live score updates
async def start_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start sending live IPL score updates every 7 minutes until the match is completed."""
    await update.message.reply_text("Starting live IPL score updates...")

    # Start sending updates in the background
    asyncio.create_task(send_live_score_periodically(update, context))


# Command handler to stop live score updates
async def stop_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop sending live IPL score updates."""
    await update.message.reply_text("Live IPL score updates stopped.")



# Main function
def main():
    """Initialize and run the bot."""
    global chat_session
    chat_session = initialize_gemini()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('ipl', ipl_command))  # New handler for IPL score
    app.add_handler(CommandHandler("startupdates", start_updates))  # Command to start updates
    app.add_handler(CommandHandler("stopupdates", stop_updates))    # Command to stop updates
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_error_handler(error)

    print('Polling...')
    app.run_polling(poll_interval=3)

if __name__ == '__main__':
    main()
