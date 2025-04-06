import asyncio
import os
import re
import google.generativeai as genai
import requests
import speech_recognition as sr
from typing import Final
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from gtts import gTTS
from datetime import timedelta
from pydub import AudioSegment

# Bot configuration
# TOKEN: Final = '1707467959:AAEVhQeYzTAlDvN_TimqMa6TFYIuZ_hy9oE'
TOKEN: Final = '1332501115:AAHOVj2bTdGydfU5ye57ktebymzufLRaSGY'
BOT_USERNAME: Final = '@Lilly007_bot'

# Google Gemini configuration
API_KEY = "AIzaSyCH4cYp_chKtFsRvIMxqNrIIbpCFQXNtkI"
MODEL_NAME = "gemini-1.5-pro"

# Cricket API configuration
CRICAPI_KEY = "c4dc1efc-789c-4d10-be83-f5f99052e16f"
CRICAPI_CURRENT_MATCHES_URL = "https://api.cricapi.com/v1/currentMatches"

# Track active score update tasks
active_updates = {}

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

# CricAPI Functions
def get_current_matches():
    """Get current matches from CricAPI grouped by match type"""
    try:
        params = {"apikey": CRICAPI_KEY}
        response = requests.get(CRICAPI_CURRENT_MATCHES_URL, params=params)
        data = response.json()
        
        # Group matches by match type
        matches_by_type = {}
        if 'data' in data:
            for match in data['data']:
                match_type = match.get('matchType', 'unknown')
                if match_type not in matches_by_type:
                    matches_by_type[match_type] = []
                matches_by_type[match_type].append(match)
                
        return matches_by_type, data['data'] if 'data' in data else []
    except Exception as e:
        print(f"Error fetching matches: {str(e)}")
        return {}, []

def get_match_score(match_id, all_matches):
    """Get score for a specific match"""
    for match in all_matches:
        if match['id'] == match_id:
            # Construct score message
            teams = match.get('teams', ['Team A', 'Team B'])
            team_1, team_2 = teams if len(teams) >= 2 else ('Team A', 'Team B')
            
            score_info = match.get('score', [])
            status = match.get('status', 'Status not available')
            venue = match.get('venue', 'Venue not available')
            
            # Format score information
            score_lines = []
            for score_entry in score_info:
                inning = score_entry.get('inning', '')
                runs = score_entry.get('r', 0)
                wickets = score_entry.get('w', 0)
                overs = score_entry.get('o', 0)
                score_lines.append(f"{inning}: {runs}/{wickets} ({overs} overs)")
            
            score_text = "\n".join(score_lines)
            
            match_info = (
                f"🏏 {match.get('name', 'Match')}\n\n"
                f"📍 {venue}\n"
                f"⏰ {match.get('date', 'Date not available')}\n"
                f"📊 Status: {status}\n\n"
                f"{score_text}"
            )
            
            return match_info
    
    return "Match information not found."

# Command handler for cricket command
async def cricket_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available cricket matches grouped by type"""
    matches_by_type, _ = get_current_matches()
    
    if not matches_by_type:
        await update.message.reply_text("No matches currently available or error fetching data.")
        return
    
    keyboard = []
    for match_type, matches in matches_by_type.items():
        # Add match type as a header button (not clickable)
        keyboard.append([InlineKeyboardButton(f"📋 {match_type.upper()} MATCHES", callback_data="header")])
        # Add each match under its type
        for match in matches:
            match_name = match.get('name', 'Unknown Match')
            match_id = match.get('id', '')
            keyboard.append([InlineKeyboardButton(match_name, callback_data=f"match_{match_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Use the appropriate method based on whether this is an initial command or a callback
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text("Select a match:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Select a match:", reply_markup=reply_markup)

# Callback query handler for inline keyboard
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == "header":
        # Header buttons do nothing
        return
    
    if callback_data == "back":
        # Go back to match selection
        await cricket_command(update, context)
        return
        
    if callback_data.startswith("match_"):
        match_id = callback_data.replace("match_", "")
        
        # Create action buttons for this match
        keyboard = [
            [
                InlineKeyboardButton("🔍 Live Score", callback_data=f"live_{match_id}"),
                InlineKeyboardButton("🔄 Start Updates", callback_data=f"update_{match_id}")
            ],
            [
                InlineKeyboardButton("⏹️ Stop Updates", callback_data=f"stop_{match_id}"),
                InlineKeyboardButton("🔙 Back", callback_data="back")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Choose an action for this match:", reply_markup=reply_markup)
    
    elif callback_data.startswith("live_"):
        match_id = callback_data.replace("live_", "")
        _, all_matches = get_current_matches()
        score = get_match_score(match_id, all_matches)
        
        # Add a back button to return to match selection
        keyboard = [[InlineKeyboardButton("🔙 Back to Matches", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(score, reply_markup=reply_markup)
    
    elif callback_data.startswith("update_"):
        match_id = callback_data.replace("update_", "")
        chat_id = update.effective_chat.id
        
        # Stop existing updates for this chat
        if chat_id in active_updates:
            active_updates[chat_id].cancel()
        
        # Start new updates
        task = asyncio.create_task(send_match_updates(context, chat_id, match_id))
        active_updates[chat_id] = task
        
        # Add a back button
        keyboard = [[InlineKeyboardButton("🔙 Back to Matches", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Started regular updates for this match. Updates will be sent every 5 minutes.\n\nUse /stop_updates to stop all updates.", 
            reply_markup=reply_markup
        )
    
    elif callback_data.startswith("stop_"):
        match_id = callback_data.replace("stop_", "")
        chat_id = update.effective_chat.id
        
        if chat_id in active_updates:
            active_updates[chat_id].cancel()
            del active_updates[chat_id]
            
            # Add a back button
            keyboard = [[InlineKeyboardButton("🔙 Back to Matches", callback_data="back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("Match updates stopped.", reply_markup=reply_markup)
        else:
            # Add a back button
            keyboard = [[InlineKeyboardButton("🔙 Back to Matches", callback_data="back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("No active updates to stop.", reply_markup=reply_markup)

async def send_match_updates(context, chat_id, match_id):
    """Send match updates every 5 minutes until match ends or updates are canceled"""
    try:
        while True:
            # Get fresh match data
            _, all_matches = get_current_matches()
            score = get_match_score(match_id, all_matches)
            
            # Check if match has ended
            match_ended = False
            for match in all_matches:
                if match['id'] == match_id and match.get('matchEnded', False):
                    match_ended = True
                    break
            
            # Create keyboard with back button for each update
            keyboard = [[InlineKeyboardButton("🔙 Back to Matches", callback_data="back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send update with back button
            await context.bot.send_message(
                chat_id=chat_id, 
                text=score,
                reply_markup=reply_markup
            )
            
            if match_ended:
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text="Match has ended. Stopping updates.",
                    reply_markup=reply_markup
                )
                break
            
            # Wait for 5 minutes
            await asyncio.sleep(300)
    
    except asyncio.CancelledError:
        # Task was cancelled, do cleanup if needed
        pass
    except Exception as e:
        # Create keyboard with back button for error message
        keyboard = [[InlineKeyboardButton("🔙 Back to Matches", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Error in match updates: {str(e)}",
            reply_markup=reply_markup
        )

# Command to stop all updates
async def stop_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop all active match updates for this chat"""
    chat_id = update.effective_chat.id
    
    if chat_id in active_updates:
        active_updates[chat_id].cancel()
        del active_updates[chat_id]
        
        # Create keyboard with match selection option
        keyboard = [[InlineKeyboardButton("🔙 See Available Matches", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("All match updates stopped.", reply_markup=reply_markup)
    else:
        # Create keyboard with match selection option
        keyboard = [[InlineKeyboardButton("🔙 See Available Matches", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("No active updates to stop.", reply_markup=reply_markup)

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

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Hello! Thanks for chatting with me! I am Lilly!\n\nUse /cricket to see live cricket matches.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "I am Lilly. Please type or send a voice message, and I will assist you!\n\n"
        "Cricket Commands:\n"
        "/cricket - View current cricket matches\n"
        "/stop_updates - Stop all match updates\n"
    )
    await update.message.reply_text(help_text)

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

# Main function
def main():
    """Initialize and run the bot."""
    global chat_session
    chat_session = initialize_gemini()

    app = Application.builder().token(TOKEN).build()
    
    # Cricket-related handlers
    app.add_handler(CommandHandler('cricket', cricket_command))
    app.add_handler(CommandHandler('stop_updates', stop_all_updates))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Standard command handlers
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    app.add_error_handler(error)

    print('Polling...')
    app.run_polling(poll_interval=3)

if __name__ == '__main__':
    main()
