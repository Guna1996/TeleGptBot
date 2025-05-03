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
import logging

# Bot configuration
for key, value in os.environ.items():
    print(f"{key}: {value[:3]}..." if value else f"{key}: None")

def unite_token(parts):
    # Join all parts together to form the original token
    token = ''.join(parts)
    return token

# Example usage:
parts = [
    "1707467959", ":", "AAG_", "z16k", "2SX", "Qxl", "0LG", "1iI", "B6I", "h7dlKweYFoTQ"
]
# TOKEN: Final = os.environ.get('BOT_TOKEN')
TOKEN: Final = unite_token(parts)
BOT_USERNAME: Final = '@Lilly007_bot'

# Google Gemini configuration
API_KEY = "AIzaSyCH4cYp_chKtFsRvIMxqNrIIbpCFQXNtkI"
MODEL_NAME = "gemini-1.5-pro"

# Cricket API configuration
CRICAPI_KEY = "b3ac3bd9-62c3-4b80-bfca-7147069f3261"
CRICAPI_CURRENT_MATCHES_URL = "https://api.cricapi.com/v1/currentMatches"

# Track active score update tasks
active_updates = {}

# Content moderation patterns (Tanglish version)
BAD_WORDS_PATTERNS = [
    r"\b(?:porn|xxx|sex|adult|free sex|thevidiya|baadu|punda|koothi|bitch|casino|gambling|bet|mayiru|mood|kami di|nude)\b",
    r"\b(?:ass|dick|fuck|slut|whore|nigga|cunt|faggot|twat|tranny|horny|sexy|bastard|bimbo|cocksucker|pussy|asshole|douchebag|cum|tits|fist|rape|murder|chutiya|gaandu|madharchod|bhenchod)\b",
    # Tanglish bad words (English + Tamil mix)
    r"\b(?:paavam|kothi|adutha level|vayadi|vittu puda|naattu kuthu|koo ra|kuduthi vaa|vaadi|pichai|nalla punda|paavi|mokka|madrasi|mutha|kutti)\b",
    r"\b(?:chuth|bitch|pundekel|u paavi|kanakku|madharchod|bhenchod|fucka|katti|bimbo|idiot|neenga paavi|suthi)\b",  # Mixed English + Tamil slurs
    r"\b(?:siru puttukal|kudumbam|yennai vaadi|piching|chitti|pichuvita)\b",  # Some colloquial/insulting phrases
]

LINK_PATTERNS = [
    r"https?://\S+",  # General URL pattern
    r"www\.\S+",  # URLs starting with www
    r"t\.me/\S+",  # Telegram links
    r"telegram\.(?:me|org|dog)/\S+",  # Different Telegram link formats
    r"@\w+",  # Potential Telegram handles
    r"join\.?\s*(?:my|our|the)?\s*(?:channel|group|chat)",  # Join invitations
    r"\b(?:click|visit|check out|join)\b.{0,30}\b(?:link|url|website|channel|group)\b",  # Link invitations
    r"\b(?:buy|discount|available|pay|service|free|job|girls|win|trading|invest|free|come|call|msg|message|promocode|advertise|buy now|di|dm|trade|offer|earn|deal|join)\b",
    # Additional patterns for scam-related content
    r"https?://(?:bit\.ly|t\.me|tinyurl\.com)/\S+",  # Shortened links for phishing
    r"bit\.ly/\S+",  # Shortened URLs for malicious content
    r"\b(?:earn|quick cash|fast money|investment|pay now|cryptocurrency|forex|buy now)\b",  # Scams or ads related to earning
    # Tanglish scam-related words and phrases
    r"\b(?:invest panna|cryptocurrency buy|fast money earn|quick cash kariya|job pannidalam|dm panna|buy sell bitcoin|easy cash earn)\b",
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
    # Add a header row with close button
    keyboard.append([
        InlineKeyboardButton("🏏 LIVE CRICKET MATCHES", callback_data="live_matches"),
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])
    
    # Add match categories with separate sections for each type
    for match_type, matches in matches_by_type.items():
        # Add match type as a header button (not clickable)
        keyboard.append([InlineKeyboardButton(f"📋 {match_type.upper()} MATCHES", callback_data=f"category_{match_type}")])
    
    # Add view all matches option
    keyboard.append([InlineKeyboardButton("👁️ View All Matches", callback_data="view_all")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Use the appropriate method based on whether this is an initial command or a callback
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text("Select a match category:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Select a match category:", reply_markup=reply_markup)

async def show_live_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show only matches that haven't ended yet"""
    _, all_matches = get_current_matches()
    
    # Filter out matches that have ended
    live_matches = [match for match in all_matches if not match.get('matchEnded', False)]
    
    if not live_matches:
        # No live matches available
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Categories", callback_data="back_to_categories")],
            [InlineKeyboardButton("❌ Close", callback_data="close")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text("No live matches currently available.", reply_markup=reply_markup)
        return
    
    # Group live matches by type for better organization
    live_matches_by_type = {}
    for match in live_matches:
        match_type = match.get('matchType', 'unknown')
        if match_type not in live_matches_by_type:
            live_matches_by_type[match_type] = []
        live_matches_by_type[match_type].append(match)
    
    keyboard = []
    # Add a header row
    keyboard.append([
        InlineKeyboardButton("🏏 LIVE MATCHES ONLY", callback_data="header"),
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])
    
    # Add matches grouped by type
    for match_type, matches in live_matches_by_type.items():
        # Add match type as a header
        keyboard.append([InlineKeyboardButton(f"📋 {match_type.upper()}", callback_data="header")])
        # Add matches under this type
        for match in matches:
            match_name = match.get('name', 'Unknown Match')
            match_id = match.get('id', '')
            keyboard.append([InlineKeyboardButton(match_name, callback_data=f"match_{match_id}")])
    
    # Add back button
    keyboard.append([InlineKeyboardButton("🔙 Back to Categories", callback_data="back_to_categories")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Select a live match:", reply_markup=reply_markup)


async def show_matches_by_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category=None):
    """Show matches filtered by category or all matches if category is None"""
    matches_by_type, _ = get_current_matches()
    
    if not matches_by_type:
        await update.callback_query.edit_message_text("No matches currently available or error fetching data.")
        return
    
    keyboard = []
    # Add a header row with close button
    keyboard.append([
        InlineKeyboardButton(f"🏏 {category.upper() if category else 'ALL'} MATCHES", callback_data="header"),
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])
    
    # If we're showing a specific category
    if category and category in matches_by_type:
        for match in matches_by_type[category]:
            match_name = match.get('name', 'Unknown Match')
            match_id = match.get('id', '')
            keyboard.append([InlineKeyboardButton(match_name, callback_data=f"match_{match_id}")])
    # If we're showing all matches
    elif not category:
        for match_type, matches in matches_by_type.items():
            # Add match type as a header
            keyboard.append([InlineKeyboardButton(f"📋 {match_type.upper()}", callback_data="header")])
            # Add matches under this type
            for match in matches:
                match_name = match.get('name', 'Unknown Match')
                match_id = match.get('id', '')
                keyboard.append([InlineKeyboardButton(match_name, callback_data=f"match_{match_id}")])
    
    # Add back button
    keyboard.append([InlineKeyboardButton("🔙 Back to Categories", callback_data="back_to_categories")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Select a match:", reply_markup=reply_markup)

# Callback query handler for inline keyboard
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    # Handle close button - delete the message
    if callback_data == "close":
        await query.delete_message()
        return
    
    if callback_data == "header":
        # Header buttons do nothing
        return
    
    if callback_data == "live_matches":
        # Show only live (not ended) matches
        await show_live_matches(update, context)
        return
    
    if callback_data == "back_to_categories":
        # Go back to match categories
        await cricket_command(update, context)
        return
        
    if callback_data == "view_all":
        # Show all matches
        await show_matches_by_category(update, context, None)
        return
        
    if callback_data.startswith("category_"):
        # Show matches for a specific category
        category = callback_data.replace("category_", "")
        # Store the current category for better back navigation
        context.user_data['last_category'] = category
        await show_matches_by_category(update, context, category)
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
                InlineKeyboardButton("🔙 Back", callback_data=f"back_from_actions_{match_id}")
            ],
            [InlineKeyboardButton("❌ Close", callback_data="close")]
        ]
        
        # Store the current state in user_data to enable proper back navigation
        if not context.user_data.get('navigation_stack'):
            context.user_data['navigation_stack'] = []
        context.user_data['navigation_stack'].append({"type": "match_actions", "match_id": match_id})
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Choose an action for this match:", reply_markup=reply_markup)
    
    elif callback_data.startswith("live_"):
        match_id = callback_data.replace("live_", "")
        _, all_matches = get_current_matches()
        score = get_match_score(match_id, all_matches)
        
        # Add back and close buttons
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Actions", callback_data=f"back_to_actions_{match_id}")],
            [InlineKeyboardButton("❌ Close", callback_data="close")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store navigation state
        if not context.user_data.get('navigation_stack'):
            context.user_data['navigation_stack'] = []
        context.user_data['navigation_stack'].append({"type": "live_score", "match_id": match_id})
        
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
        
        # Add back and close buttons
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Actions", callback_data=f"back_to_actions_{match_id}")],
            [InlineKeyboardButton("❌ Close", callback_data="close")]
        ]
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
            
            # Add back and close buttons
            keyboard = [
                [InlineKeyboardButton("🔙 Back to Actions", callback_data=f"back_to_actions_{match_id}")],
                [InlineKeyboardButton("❌ Close", callback_data="close")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("Match updates stopped.", reply_markup=reply_markup)
        else:
            # Add back and close buttons
            keyboard = [
                [InlineKeyboardButton("🔙 Back to Actions", callback_data=f"back_to_actions_{match_id}")],
                [InlineKeyboardButton("❌ Close", callback_data="close")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("No active updates to stop.", reply_markup=reply_markup)
    
    # Handle various back navigation patterns
    elif callback_data.startswith("back_from_actions_"):
        match_id = callback_data.replace("back_from_actions_", "")
        # Get the category from context if possible
        if context.user_data.get('last_category'):
            await show_matches_by_category(update, context, context.user_data.get('last_category'))
        else:
            # If no category stored, go to all matches
            await show_matches_by_category(update, context, None)
    
    elif callback_data.startswith("back_to_actions_"):
        match_id = callback_data.replace("back_to_actions_", "")
        
        # Go back to match actions
        keyboard = [
            [
                InlineKeyboardButton("🔍 Live Score", callback_data=f"live_{match_id}"),
                InlineKeyboardButton("🔄 Start Updates", callback_data=f"update_{match_id}")
            ],
            [
                InlineKeyboardButton("⏹️ Stop Updates", callback_data=f"stop_{match_id}"),
                InlineKeyboardButton("🔙 Back", callback_data=f"back_from_actions_{match_id}")
            ],
            [InlineKeyboardButton("❌ Close", callback_data="close")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Choose an action for this match:", reply_markup=reply_markup)

async def send_match_updates(context, chat_id, match_id):
    """Send match updates every 5 minutes until match ends or updates are canceled"""
    try:
        # Variable to store the previous message ID
        previous_message_id = None
        
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
            
            # Create keyboard with back and close buttons for each update
            keyboard = [
                [InlineKeyboardButton("🔙 Back to Matches", callback_data="back_to_categories")],
                [InlineKeyboardButton("❌ Close", callback_data="close")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Delete previous update message if it exists
            if previous_message_id:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=previous_message_id)
                except Exception as e:
                    # If deletion fails, continue anyway
                    print(f"Could not delete previous message: {str(e)}")
            
            # Send new update message
            new_message = await context.bot.send_message(
                chat_id=chat_id, 
                text=score,
                reply_markup=reply_markup
            )
            
            # Store the new message ID for deletion next time
            previous_message_id = new_message.message_id
            
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
        # Create keyboard with back and close buttons for error message
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Matches", callback_data="back_to_categories")],
            [InlineKeyboardButton("❌ Close", callback_data="close")]
        ]
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
        
        # Create keyboard with match selection option and close button
        keyboard = [
            [InlineKeyboardButton("🔙 See Available Matches", callback_data="back_to_categories")],
            [InlineKeyboardButton("❌ Close", callback_data="close")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("All match updates stopped.", reply_markup=reply_markup)
    else:
        # Create keyboard with match selection option and close button
        keyboard = [
            [InlineKeyboardButton("🔙 See Available Matches", callback_data="back_to_categories")],
            [InlineKeyboardButton("❌ Close", callback_data="close")]
        ]
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
    
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome new members with an animation and message in Tamil."""
    for new_member in update.message.new_chat_members:
        # Skip if the new member is the bot itself
        if new_member.id == context.bot.id:
            continue
            
        # Get user info and create proper mention tag
        user_first_name = new_member.first_name
        user_mention = f"[{new_member.first_name}](tg://user?id={new_member.id})"
        
        # First try sending a welcome GIF/sticker
        try:
            # You can use local files or file_ids as discussed earlier
            sticker_id = "CAACAgIAAxkBAAEB_ENj3npGnr7A2jwj9m1IvYKCwGEDAALeAgACVp29CkAGJPXELhFtLwQ"  # Replace with your sticker ID
            await context.bot.send_sticker(
                chat_id=update.effective_chat.id,
                sticker=sticker_id
            )
        except Exception as e:
            print(f"Error sending sticker: {e}")
        
        # Then do the animated text welcome
        try:
            await tamil_animated_welcome_message(update, context, user_first_name, user_mention)
        except Exception as e:
            print(f"Animation failed, sending normal welcome: {e}")
            # Fallback to normal welcome message with inline keyboard
            welcome_text = (
                f"🌟 வணக்கம் {user_mention}! எங்கள் குழுவிற்கு உங்களை வரவேற்கிறோம்! 🌟\n\n"
                f"நீங்கள் எங்களுடன் இணைந்ததில் மிக்க மகிழ்ச்சி! உங்களை அறிமுகப்படுத்திக் கொள்ளுங்கள்."
            )
            
            # Create inline keyboard
            keyboard = create_welcome_inline_keyboard()
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=welcome_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )

async def tamil_animated_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_name: str, user_mention: str):
    """Send a welcome message in Tamil that appears character by character."""
    # Welcome message content in Tamil
    welcome_text = (
        f"வணக்கம் {user_name}! எங்கள் குழுவிற்கு உங்களை வரவேற்கிறோம்! 🌟\n\n"
        f"நீங்கள் எங்களுடன் இணைந்ததில் மிக்க மகிழ்ச்சி! உங்களை அறிமுகப்படுத்திக் கொள்ளுங்கள்."
    )
    
    # Send initial empty message
    message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="..."
    )
    
    # Start with empty text
    current_text = ""
    
    # Add one character at a time
    for char in welcome_text:
        current_text += char
        
        try:
            # Edit message with updated text
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=message.message_id,
                text=current_text
            )
            
            # Very short delay between characters
            delay = 0.1 if char in ['.', '!', '?', '\n'] else 0.05
            await asyncio.sleep(delay)  # Adjust timing to avoid rate limits
            
        except Exception as e:
            print(f"Error in animation: {e}")
            # If editing fails, complete the message immediately
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message.message_id,
                    text=welcome_text
                )
            except:
                pass  # If final edit fails, just continue
            break
    
    # After animation completes, add inline keyboard
    try:
        final_welcome_text = (
            f"வணக்கம் {user_mention}! எங்கள் குழுவிற்கு உங்களை வரவேற்கிறோம்! 🌟\n\n"
            f"நீங்கள் எங்களுடன் இணைந்ததில் மிக்க மகிழ்ச்சி! உங்களை அறிமுகப்படுத்திக் கொள்ளுங்கள்."
        )
        
        keyboard = create_welcome_inline_keyboard()
        
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=message.message_id,
            text=final_welcome_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Error adding inline keyboard: {e}")
        # If adding keyboard fails, just continue with the text message

def create_welcome_inline_keyboard():
    """Create an inline keyboard with buttons for help, cricket, and other functions."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = [
        [
            InlineKeyboardButton("உதவி 🤔", callback_data="help"),
            InlineKeyboardButton("கிரிக்கெட் 🏏", callback_data="cricket")
        ],
        [
            InlineKeyboardButton("விதிமுறைகள் 📜", callback_data="rules"),
            InlineKeyboardButton("லில்லியை அழைக்க 🤖", url="https://t.me/Lilly007_bot")
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)

# Callback handler for inline keyboard buttons
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses from inline keyboards."""
    query = update.callback_query
    await query.answer()  # Answer the callback query to stop the loading animation
    
    if query.data == "help":
        help_text = (
            "🔍 *உதவி மெனு* 🔍\n\n"
            "• /help - உதவி மெனுவைக் காட்டும்\n"
            "• /cricket - கிரிக்கெட் தகவல்கள் பெறுங்கள்\n"
            "• /rules - குழு விதிமுறைகளைக் காட்டும்\n"
        )
        await query.edit_message_text(
            text=help_text,
            parse_mode="Markdown",
            reply_markup=create_welcome_inline_keyboard()
        )
    
    elif query.data == "cricket":
        cricket_text = (
            "🏏 *கிரிக்கெட் தகவல்கள்* 🏏\n\n"
            "தற்போதைய கிரிக்கெட் தகவல்கள் பெற:\n"
            "• /cricket score - தற்போதைய ஸ்கோர்\n"
            "• /cricket schedule - வரவிருக்கும் போட்டிகள்\n"
            "• /cricket news - சமீபத்திய செய்திகள்"
        )
        await query.edit_message_text(
            text=cricket_text,
            parse_mode="Markdown",
            reply_markup=create_welcome_inline_keyboard()
        )
    
    elif query.data == "rules":
        rules_text = (
            "📜 *குழு விதிமுறைகள்* 📜\n\n"
            "1. மற்றவர்களை மதியுங்கள்\n"
            "2. ஸ்பாம் அனுப்ப வேண்டாம்\n"
            "3. தகுந்த தலைப்புகளைப் பற்றி மட்டுமே விவாதிக்கவும்\n"
            "4. தனிப்பட்ட தகவல்களைப் பகிர வேண்டாம்\n"
            "5. விதிகளை மீறினால் எச்சரிக்கை பெறுவீர்கள்"
        )
        await query.edit_message_text(
            text=rules_text,
            parse_mode="Markdown",
            reply_markup=create_welcome_inline_keyboard()
        )

# Main function
def main():
    """Initialize and run the bot."""
    global chat_session
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    # Define the logger
    logger = logging.getLogger(__name__)
    chat_session = initialize_gemini()
    if TOKEN:
        # Log first 5 and last 3 characters only for security
        token_preview = TOKEN[:5] + "..." + TOKEN[-3:]
        logger.info(f"Token configured: {token_preview}")
    else:
        logger.error("TOKEN is empty or not configured!")
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

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    
    app.add_error_handler(error)

    print('Polling...')
    app.run_polling(poll_interval=3)

if __name__ == '__main__':
    main()
