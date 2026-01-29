import logging
import re
import os
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, InputMediaPhoto
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.error import TelegramError

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
import psutil

from pyrogram import Client
from pyrogram.types import Message as PyrogramMessage
from pyrogram.errors import FloodWait

import aiohttp
import hashlib

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "sh_bot_db")

# Pyrogram (for indexing old messages)
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_SESSION = os.getenv("BOT_SESSION", "sh_bot_session")

# Channels
CH_SINHALA_SUB = int(os.getenv("CH_SINHALA_SUB", "0"))
CH_PC_GAME = int(os.getenv("CH_PC_GAME", "0"))
CH_MOVIE_SERIES = int(os.getenv("CH_MOVIE_SERIES", "0"))

# Update Channel (where movie cards are posted)
UPDATE_CHANNEL = int(os.getenv("UPDATE_CHANNEL", "0"))

# Authorized Group
AUTHORIZED_GROUP_ID = int(os.getenv("AUTHORIZED_GROUP_ID", "0"))

# Links
GROUP_LINK = os.getenv("GROUP_LINK", "https://t.me/YourGroup")
START_IMAGE = os.getenv("START_IMAGE", "https://graph.org/file/abc123.jpg")

# TMDB API
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

# Features
AUTO_UPDATE_CHANNEL = os.getenv("AUTO_UPDATE_CHANNEL", "true").lower() == "true"
MAINTENANCE_MODE = False

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- MONGODB CLIENT ---
mongo_client = None
db = None

async def init_db():
    global mongo_client, db
    mongo_client = AsyncIOMotorClient(MONGODB_URI)
    db = mongo_client[DB_NAME]
    
    # Create indexes
    await db.files.create_index("file_unique_id", unique=True)
    await db.files.create_index("file_name")
    await db.files.create_index([("file_name", "text")])
    await db.files.create_index("category")
    await db.users.create_index("user_id", unique=True)
    await db.admins.create_index("user_id", unique=True)
    
    # Add owner as admin
    await db.admins.update_one(
        {"user_id": OWNER_ID},
        {"$set": {"user_id": OWNER_ID, "added_date": datetime.now()}},
        upsert=True
    )
    
    logger.info("✅ Database initialized")

# --- DATABASE HELPERS ---
async def is_admin(user_id: int) -> bool:
    result = await db.admins.find_one({"user_id": user_id})
    return result is not None

async def is_premium_user(user_id: int) -> bool:
    user = await db.users.find_one({"user_id": user_id})
    if user and user.get("premium", False):
        expiry = user.get("premium_expiry")
        if expiry and expiry > datetime.now():
            return True
    return False

async def get_stats() -> Dict:
    users_count = await db.users.count_documents({})
    groups_count = await db.groups.count_documents({})
    files_count = await db.files.count_documents({})
    premium_count = await db.users.count_documents({
        "premium": True,
        "premium_expiry": {"$gt": datetime.now()}
    })
    
    # Storage info (approximate)
    db_stats = await db.command("dbStats")
    used_storage = db_stats.get("dataSize", 0) / (1024 * 1024)  # MB
    
    return {
        "users": users_count,
        "groups": groups_count,
        "files": files_count,
        "premium": premium_count,
        "used_storage": used_storage
    }

# --- TMDB API ---
async def search_tmdb(query: str, media_type: str = "movie") -> Optional[Dict]:
    """Search TMDB for movie/series details"""
    if not TMDB_API_KEY:
        return None
    
    url = f"https://api.themoviedb.org/3/search/{media_type}"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "en-US"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("results"):
                        return data["results"][0]
    except Exception as e:
        logger.error(f"TMDB search error: {e}")
    
    return None

async def get_tmdb_details(tmdb_id: int, media_type: str = "movie") -> Optional[Dict]:
    """Get detailed info from TMDB"""
    if not TMDB_API_KEY:
        return None
    
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": "en-US"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.error(f"TMDB details error: {e}")
    
    return None

# --- TEXT PROCESSING ---
def get_readable_size(size_in_bytes):
    if not size_in_bytes:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} PB"

def clean_filename(text: str) -> str:
    """Clean and format filename"""
    if not text:
        return "Unknown File"
    
    # Remove links, usernames, quality tags
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'(https?://\S+|www\.\S+|t\.me/\S+)', '', text)
    text = re.sub(r'(?i)(1080p|720p|480p|BluRay|WEB-DL|x264|x265|HEVC|AAC|DDP5\.1|\.mkv|\.mp4|\.avi)', '', text)
    
    # Replace symbols with space
    text = re.sub(r'[._\-]', ' ', text)
    text = re.sub(r'[\[\]\(\)]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def extract_quality(filename: str) -> str:
    """Extract quality from filename"""
    qualities = ["2160p", "1080p", "720p", "480p", "360p"]
    for q in qualities:
        if q.lower() in filename.lower():
            return q
    return "Unknown"

def extract_audio(filename: str) -> str:
    """Extract audio format"""
    audio_formats = ["AAC", "DDP5.1", "DD5.1", "AC3", "DTS", "FLAC"]
    for fmt in audio_formats:
        if fmt.lower() in filename.lower():
            return fmt
    return "Unknown"

def extract_metadata(text: str) -> tuple:
    """Extract Season and Episode"""
    s, e = 0, 0
    s_match = re.search(r'(?:s|season)\s?(\d{1,2})', text, re.IGNORECASE)
    e_match = re.search(r'(?:e|episode|ep)\s?(\d{1,3})', text, re.IGNORECASE)
    
    if s_match:
        s = int(s_match.group(1))
    if e_match:
        e = int(e_match.group(1))
    
    return s, e

def determine_category(chat_id: int, file_name: str) -> str:
    """Determine file category"""
    if chat_id == CH_PC_GAME:
        return "Games"
    elif chat_id == CH_SINHALA_SUB:
        return "SinhalaSub"
    elif chat_id == CH_MOVIE_SERIES:
        if re.search(r'(S\d+|Season|E\d+|Episode)', file_name, re.IGNORECASE):
            return "Series"
        return "Movies"
    return "Others"

# --- AUTO-DELETE MESSAGE ---
async def auto_delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = 300):
    """Delete message after delay (default 5 minutes)"""
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    # Register user
    await db.users.update_one(
        {"user_id": user.id},
        {"$set": {
            "user_id": user.id,
            "first_name": user.first_name,
            "username": user.username,
            "joined_date": datetime.now()
        }},
        upsert=True
    )
    
    # File download (deep link)
    if args and args[0].startswith("file_"):
        if MAINTENANCE_MODE and not await is_admin(user.id):
            msg = await update.message.reply_text("🚧 System is under maintenance.")
            asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
            return
        
        file_db_id = args[0].split("_")[1]
        file_data = await db.files.find_one({"_id": file_db_id})
        
        if file_data:
            # Update history
            await db.history.insert_one({
                "user_id": user.id,
                "file_name": file_data["file_name"],
                "file_id": file_data["_id"],
                "dl_date": datetime.now()
            })
            
            # Keep only last 10
            history_list = await db.history.find({"user_id": user.id}).sort("_id", -1).to_list(length=None)
            if len(history_list) > 10:
                delete_ids = [h["_id"] for h in history_list[10:]]
                await db.history.delete_many({"_id": {"$in": delete_ids}})
            
            caption = (
                f"📂 **{file_data['file_name']}**\n\n"
                f"🗂 **Category:** {file_data['category']}\n"
                f"💾 **Size:** {get_readable_size(file_data.get('file_size', 0))}\n"
                f"🤖 **Downloaded via SH BOTS**"
            )
            
            try:
                if file_data.get("file_type") == "video":
                    msg = await update.message.reply_video(
                        video=file_data["file_id"],
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    msg = await update.message.reply_document(
                        document=file_data["file_id"],
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
            except Exception as e:
                msg = await update.message.reply_text("❌ File not available or deleted.")
                asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
                logger.error(f"Send error: {e}")
        else:
            msg = await update.message.reply_text("❌ File not found.")
            asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
        return
    
    # Private chat start
    if update.effective_chat.type == ChatType.PRIVATE:
        if await is_admin(user.id):
            await show_admin_dashboard(update, context)
        else:
            stats = await get_stats()
            text = (
                f"👋 **Welcome {user.first_name}!**\n\n"
                f"🗂 **Total Files:** `{stats['files']}`\n"
                f"⚠️ **Access Restricted:**\n"
                f"මෙම බොට් භාවිතා කළ හැක්කේ අපගේ Group එක හරහා පමණි.\n\n"
                f"👇 **Join Group or View Help:**"
            )
            kb = [
                [InlineKeyboardButton("🔗 Join SH Film & Game Group", url=GROUP_LINK)],
                [InlineKeyboardButton("❓ Commands & Help", callback_data="user_help")]
            ]
            
            try:
                msg = await update.message.reply_photo(
                    photo=START_IMAGE,
                    caption=text,
                    reply_markup=InlineKeyboardMarkup(kb),
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                msg = await update.message.reply_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(kb),
                    parse_mode=ParseMode.MARKDOWN
                )
            asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
    
    # Group welcome
    elif update.effective_chat.id == AUTHORIZED_GROUP_ID:
        # Register group
        await db.groups.update_one(
            {"group_id": update.effective_chat.id},
            {"$set": {
                "group_id": update.effective_chat.id,
                "title": update.effective_chat.title,
                "joined_date": datetime.now()
            }},
            upsert=True
        )
        msg = await update.message.reply_text("👋 Hi! Type any Movie/Series/Game name to search.")
        asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))

# --- SEARCH HANDLER ---
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg_text = update.message.text
    
    # Admin force reply handling
    if update.message.reply_to_message:
        reply_text = update.message.reply_to_message.text
        if "Please reply with the User ID" in reply_text and await is_admin(user.id):
            try:
                new_admin_id = int(msg_text)
                await db.admins.update_one(
                    {"user_id": new_admin_id},
                    {"$set": {"user_id": new_admin_id, "added_date": datetime.now()}},
                    upsert=True
                )
                msg = await update.message.reply_text(f"✅ User `{new_admin_id}` is now an Admin!")
                asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
            except ValueError:
                msg = await update.message.reply_text("❌ Invalid ID.")
                asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
            return
    
    if not msg_text or msg_text.startswith("/"):
        return
    
    # Access control
    if chat.type == ChatType.PRIVATE:
        if not await is_admin(user.id):
            msg = await update.message.reply_text(f"⚠️ Please use the group: {GROUP_LINK}")
            asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
            return
    elif chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        if chat.id != AUTHORIZED_GROUP_ID:
            return
    
    context.user_data['search_query'] = msg_text
    
    # Search in database
    pipeline = [
        {"$match": {"file_name": {"$regex": msg_text, "$options": "i"}}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ]
    
    results = await db.files.aggregate(pipeline).to_list(length=None)
    
    if not results:
        msg = await update.message.reply_text("❌ No results found.")
        asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
        return
    
    # Build category buttons
    keyboard = []
    row = []
    found_cats = {r["_id"]: r["count"] for r in results}
    priority = ["SinhalaSub", "Movies", "Series", "Games"]
    
    for cat in priority:
        if cat in found_cats:
            row.append(InlineKeyboardButton(f"{cat} ({found_cats[cat]})", callback_data=f"list_{cat}_0"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
    
    for cat, count in found_cats.items():
        if cat not in priority:
            row.append(InlineKeyboardButton(f"{cat} ({count})", callback_data=f"list_{cat}_0"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
    
    if row:
        keyboard.append(row)
    
    msg = await update.message.reply_text(
        f"🔎 **Search Results for:** `{msg_text}`\n👇 **Select a Category:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))

# --- CALLBACK HANDLER ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    search_query = context.user_data.get('search_query', "")
    
    # User help
    if data == "user_help":
        msg_text = (
            "🤖 **USER HELP GUIDE**\n\n"
            "🔹 **How to Search?**\n"
            "Join our group and type the Movie/Series/Game name.\n\n"
            "🔹 **Commands:**\n"
            "`/request <Name>` - Request missing file\n"
            "`/clone` - Request bot source code\n"
            "`/history` - View last 10 downloads\n\n"
            f"🔗 Group: {GROUP_LINK}"
        )
        kb = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]
        await query.edit_message_caption(
            caption=msg_text,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    elif data == "back_to_start":
        # Re-trigger start
        await query.message.delete()
        return
    
    # File listing
    elif data.startswith("list_"):
        _, cat, page = data.split("_")
        page = int(page)
        
        if cat == "Series" and "filter_season" not in context.user_data:
            context.user_data['filter_season'] = None
            context.user_data['filter_episode'] = None
        
        await render_file_list(update, context, cat, search_query, page)
    
    # Series filters
    elif data == "ser_show_seasons":
        await render_series_filter_list(update, context, "Season", search_query, 0)
    
    elif data == "ser_show_episodes":
        await render_series_filter_list(update, context, "Episode", search_query, 0)
    
    elif data.startswith("ser_pg_"):
        _, _, f_type, page = data.split("_")
        await render_series_filter_list(update, context, f_type, search_query, int(page))
    
    elif data.startswith("ser_sel_"):
        _, _, f_type, val = data.split("_")
        val = int(val)
        
        if f_type == "S":
            context.user_data['filter_season'] = val
            context.user_data['filter_episode'] = None
        elif f_type == "E":
            context.user_data['filter_episode'] = val
        
        await render_file_list(update, context, "Series", search_query, 0)
    
    elif data == "ser_clear":
        context.user_data['filter_season'] = None
        context.user_data['filter_episode'] = None
        await render_file_list(update, context, "Series", search_query, 0)
    
    # Admin actions
    elif data.startswith("adm_"):
        if not await is_admin(user_id):
            await query.answer("⚠️ Admins Only!", show_alert=True)
            return
        await handle_admin_logic(update, context)

# --- RENDER FILE LIST ---
async def render_file_list(update, context, category, query_text, page):
    limit = 10
    skip = page * limit
    
    # Build query
    match_query = {
        "file_name": {"$regex": query_text, "$options": "i"},
        "category": category
    }
    
    # Series filters
    s_filter = context.user_data.get('filter_season')
    e_filter = context.user_data.get('filter_episode')
    
    if category == "Series":
        if s_filter:
            match_query["season"] = s_filter
        if e_filter:
            match_query["episode"] = e_filter
    
    total = await db.files.count_documents(match_query)
    files = await db.files.find(match_query).sort([
        ("season", 1), ("episode", 1), ("file_name", 1)
    ]).skip(skip).limit(limit).to_list(length=limit)
    
    # Build keyboard
    kb = []
    
    # Series filter buttons
    if category == "Series":
        filter_row = [
            InlineKeyboardButton("📅 Seasons", callback_data="ser_show_seasons"),
            InlineKeyboardButton("🎞 Episodes", callback_data="ser_show_episodes")
        ]
        kb.append(filter_row)
        
        status = []
        if s_filter:
            status.append(f"✅ S{s_filter}")
        if e_filter:
            status.append(f"✅ E{e_filter}")
        if status:
            kb.append([InlineKeyboardButton(" ".join(status) + " (Clear)", callback_data="ser_clear")])
    
    # File buttons
    bot_username = context.bot.username
    for f in files:
        fname = f["file_name"]
        fsize = get_readable_size(f.get("file_size", 0))
        
        display = fname
        if category == "Series":
            s, e = f.get("season", 0), f.get("episode", 0)
            meta = ""
            if s > 0:
                meta += f"S{s:02}"
            if e > 0:
                meta += f" E{e:02}"
            if meta:
                display = f"[{meta}] {fname[:20]}..."
        else:
            display = fname[:30] + "..."
        
        url = f"https://t.me/{bot_username}?start=file_{f['_id']}"
        kb.append([InlineKeyboardButton(f"{display} ({fsize})", url=url)])
    
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Back", callback_data=f"list_{category}_{page-1}"))
    if (skip + limit) < total:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"list_{category}_{page+1}"))
    if nav_row:
        kb.append(nav_row)
    
    msg_text = f"📂 **{category}**\n🔎 Query: `{query_text}`\n📊 Found: {total} (Page {page+1})"
    
    await update.callback_query.edit_message_text(
        msg_text,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.MARKDOWN
    )

async def render_series_filter_list(update, context, filter_type, query_text, page):
    limit = 10
    skip = page * limit
    
    col = "season" if filter_type == "Season" else "episode"
    
    # Get distinct values
    pipeline = [
        {"$match": {
            "file_name": {"$regex": query_text, "$options": "i"},
            "category": "Series",
            col: {"$gt": 0}
        }},
        {"$group": {"_id": f"${col}"}},
        {"$sort": {"_id": 1}}
    ]
    
    all_vals = await db.files.aggregate(pipeline).to_list(length=None)
    total = len(all_vals)
    current_slice = all_vals[skip:skip + limit]
    
    kb = []
    row = []
    for item in current_slice:
        val = item["_id"]
        prefix = "S" if filter_type == "Season" else "E"
        cb = f"ser_sel_{prefix}_{val}"
        row.append(InlineKeyboardButton(f"{prefix}{val:02}", callback_data=cb))
        if len(row) == 5:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    
    # Navigation
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"ser_pg_{filter_type}_{page-1}"))
    if (skip + limit) < total:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"ser_pg_{filter_type}_{page+1}"))
    if nav_row:
        kb.append(nav_row)
    
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="list_Series_0")])
    
    await update.callback_query.edit_message_text(
        f"🔢 Select {filter_type}",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# --- ADMIN DASHBOARD ---
async def show_admin_dashboard(update, context):
    stats = await get_stats()
    
    # System stats
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    uptime_seconds = time.time() - psutil.boot_time()
    uptime = str(timedelta(seconds=int(uptime_seconds)))
    
    # Storage
    disk = psutil.disk_usage('/')
    free_storage = disk.free / (1024 * 1024)  # MB
    
    maint = "🔴 On" if MAINTENANCE_MODE else "🟢 Off"
    
    text = (
        f"╭────[ 🗃 ᴅᴀᴛᴀʙᴀsᴇ 🗃 ]────⍟\n"
        f"│\n"
        f"├⋟ ᴀʟʟ ᴜsᴇʀs ⋟ {stats['users']}\n"
        f"├⋟ ᴀʟʟ ɢʀᴏᴜᴘs ⋟ {stats['groups']}\n"
        f"├⋟ ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs ⋟ {stats['premium']}\n"
        f"├⋟ ᴀʟʟ ꜰɪʟᴇs ⋟ {stats['files']}\n"
        f"├⋟ ᴜsᴇᴅ sᴛᴏʀᴀɢᴇ ⋟ {stats['used_storage']:.2f} MB\n"
        f"├⋟ ꜰʀᴇᴇ sᴛᴏʀᴀɢᴇ ⋟ {free_storage:.2f} MB\n"
        f"│\n"
        f"├────[ 🤖 ʙᴏᴛ ᴅᴇᴛᴀɪʟs 🤖 ]────⍟\n"
        f"│\n"
        f"├⋟ ᴜᴘᴛɪᴍᴇ ⋟ {uptime}\n"
        f"├⋟ ʀᴀᴍ ⋟ {ram}%\n"
        f"├⋟ ᴄᴘᴜ ⋟ {cpu}%\n"
        f"├⋟ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ⋟ {maint}\n"
        f"│\n"
        f"╰─────────────────────⍟"
    )
    
    kb = [
        [InlineKeyboardButton("👁 File Requests", callback_data="adm_view_req"),
         InlineKeyboardButton("🤖 Clone Requests", callback_data="adm_view_clones")],
        [InlineKeyboardButton("➕ Add Admin", callback_data="adm_add_admin"),
         InlineKeyboardButton("➖ Remove Admin", callback_data="adm_remove_admin")],
        [InlineKeyboardButton("🛠 Toggle Maint", callback_data="adm_toggle_maint"),
         InlineKeyboardButton("📢 Toggle Updates", callback_data="adm_toggle_update")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="adm_refresh")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN
        )

# --- ADMIN LOGIC ---
async def handle_admin_logic(update, context):
    query = update.callback_query
    data = query.data
    
    if data == "adm_dashboard" or data == "adm_refresh":
        await show_admin_dashboard(update, context)
    
    elif data == "adm_toggle_maint":
        global MAINTENANCE_MODE
        MAINTENANCE_MODE = not MAINTENANCE_MODE
        await show_admin_dashboard(update, context)
    
    elif data == "adm_toggle_update":
        global AUTO_UPDATE_CHANNEL
        AUTO_UPDATE_CHANNEL = not AUTO_UPDATE_CHANNEL
        await show_admin_dashboard(update, context)
    
    elif data == "adm_add_admin":
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="🆔 Please reply with the User ID to add as Admin:",
            reply_markup=ForceReply(selective=True)
        )
        await query.answer("Check your messages.")
    
    elif data == "adm_remove_admin":
        # List admins
        admins = await db.admins.find({}).to_list(length=None)
        if len(admins) <= 1:
            await query.answer("Cannot remove all admins!", show_alert=True)
            return
        
        text = "👥 **Current Admins:**\n\n"
        kb = []
        for adm in admins:
            if adm["user_id"] != OWNER_ID:
                text += f"• ID: `{adm['user_id']}`\n"
                kb.append([InlineKeyboardButton(
                    f"❌ Remove {adm['user_id']}",
                    callback_data=f"adm_rem_{adm['user_id']}"
                )])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="adm_dashboard")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("adm_rem_"):
        admin_id = int(data.split("_")[2])
        if admin_id != OWNER_ID:
            await db.admins.delete_one({"user_id": admin_id})
        await show_admin_dashboard(update, context)
    
    # File Requests
    elif data == "adm_view_req":
        reqs = await db.requests.find({"status": "pending"}).limit(5).to_list(length=5)
        
        if not reqs:
            await query.answer("No pending requests.", show_alert=True)
            return
        
        text = "📥 **Pending File Requests**\n\n"
        kb = []
        for r in reqs:
            text += f"🔹 {r.get('user_name', 'User')}: {r['request_text']}\n"
            kb.append([
                InlineKeyboardButton(f"✅ Done", callback_data=f"adm_rdone_{r['_id']}"),
                InlineKeyboardButton(f"❌ Cancel", callback_data=f"adm_rcanc_{r['_id']}")
            ])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="adm_dashboard")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("adm_rdone_") or data.startswith("adm_rcanc_"):
        action = data.split("_")[1]
        req_id = data.split("_")[2]
        
        req = await db.requests.find_one({"_id": req_id})
        if req:
            uid = req["user_id"]
            rtext = req["request_text"]
            
            if action == "rdone":
                try:
                    await context.bot.send_message(
                        uid,
                        f"✅ **Request Fulfilled!**\n\n`{rtext}` is now available. Search in bot!",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
            else:
                try:
                    await context.bot.send_message(
                        uid,
                        f"❌ **Request Unavailable**\n\nSorry, `{rtext}` not found.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
            
            await db.requests.delete_one({"_id": req_id})
        
        await show_admin_dashboard(update, context)
    
    # Clone Requests
    elif data == "adm_view_clones":
        clones = await db.clone_requests.find({"status": "pending"}).limit(5).to_list(length=5)
        
        if not clones:
            await query.answer("No clone requests.", show_alert=True)
            return
        
        text = "🤖 **Clone Requests**\n\n"
        kb = []
        for c in clones:
            text += f"🔸 {c.get('user_name', 'User')} (ID: {c['user_id']})\n"
            kb.append([
                InlineKeyboardButton(f"✅ Approve", callback_data=f"adm_cdone_{c['_id']}"),
                InlineKeyboardButton(f"❌ Deny", callback_data=f"adm_ccanc_{c['_id']}")
            ])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="adm_dashboard")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("adm_cdone_"):
        req_id = data.split("_")[2]
        req = await db.clone_requests.find_one({"_id": req_id})
        
        if req:
            await send_source_code(context, req["user_id"])
            await db.clone_requests.delete_one({"_id": req_id})
        
        await show_admin_dashboard(update, context)
    
    elif data.startswith("adm_ccanc_"):
        req_id = data.split("_")[2]
        req = await db.clone_requests.find_one({"_id": req_id})
        
        if req:
            try:
                await context.bot.send_message(req["user_id"], "❌ Clone request denied.")
            except:
                pass
            await db.clone_requests.delete_one({"_id": req_id})
        
        await show_admin_dashboard(update, context)

async def send_source_code(context, user_id):
    """Send bot source code"""
    try:
        await context.bot.send_message(
            user_id,
            "📜 **Bot Source Code**\n\nSource code is available at:\nhttps://github.com/yourusername/sh-bot\n\n"
            "Note: Configure your own tokens and MongoDB."
        )
    except Exception as e:
        logger.error(f"Failed to send code: {e}")

# --- CHANNEL POST HANDLER (AUTO-INDEX) ---
async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-index new posts from channels"""
    msg = update.channel_post
    chat_id = msg.chat.id
    
    if chat_id not in [CH_SINHALA_SUB, CH_PC_GAME, CH_MOVIE_SERIES]:
        return
    
    file_id, unique_id, fname, fsize, ftype = None, None, "Unknown", 0, "doc"
    
    if msg.document:
        file_id = msg.document.file_id
        unique_id = msg.document.file_unique_id
        fname = msg.document.file_name or "Document"
        fsize = msg.document.file_size
    elif msg.video:
        file_id = msg.video.file_id
        unique_id = msg.video.file_unique_id
        fname = msg.video.file_name or msg.caption or "Video"
        fsize = msg.video.file_size
        ftype = "video"
    else:
        return
    
    # Check duplicate
    exists = await db.files.find_one({"file_unique_id": unique_id})
    if exists:
        return
    
    # Process metadata
    clean_name = clean_filename(fname)
    category = determine_category(chat_id, clean_name)
    season, episode = extract_metadata(fname)
    quality = extract_quality(fname)
    audio = extract_audio(fname)
    
    # Prepare file document
    file_doc = {
        "_id": str(hash(unique_id))[:16],
        "file_id": file_id,
        "file_unique_id": unique_id,
        "file_name": clean_name,
        "file_size": fsize,
        "file_type": ftype,
        "category": category,
        "season": season,
        "episode": episode,
        "quality": quality,
        "audio": audio,
        "message_id": msg.message_id,
        "channel_id": chat_id,
        "indexed_date": datetime.now()
    }
    
    try:
        await db.files.insert_one(file_doc)
        logger.info(f"✅ Indexed: {clean_name} | {category}")
        
        # Post to update channel if enabled
        if AUTO_UPDATE_CHANNEL and UPDATE_CHANNEL:
            await post_to_update_channel(context, file_doc, fname)
    
    except DuplicateKeyError:
        pass
    except Exception as e:
        logger.error(f"Index error: {e}")

async def post_to_update_channel(context, file_doc, original_fname):
    """Post file card to update channel with TMDB details"""
    try:
        # Search TMDB
        search_name = clean_filename(original_fname)
        media_type = "tv" if file_doc["category"] == "Series" else "movie"
        
        tmdb_result = await search_tmdb(search_name, media_type)
        
        if tmdb_result:
            tmdb_id = tmdb_result.get("id")
            details = await get_tmdb_details(tmdb_id, media_type)
            
            if details:
                # Build caption
                title = details.get("title") or details.get("name", "Unknown")
                overview = details.get("overview", "No description available.")[:200]
                rating = details.get("vote_average", 0)
                release = details.get("release_date") or details.get("first_air_date", "Unknown")
                genres = ", ".join([g["name"] for g in details.get("genres", [])])
                
                caption = (
                    f"🎬 **{title}**\n\n"
                    f"📝 {overview}...\n\n"
                    f"⭐ **Rating:** {rating}/10\n"
                    f"📅 **Release:** {release}\n"
                    f"🎭 **Genres:** {genres}\n"
                    f"🎞 **Quality:** {file_doc['quality']}\n"
                    f"🔊 **Audio:** {file_doc['audio']}\n"
                )
                
                if file_doc["category"] == "Series":
                    caption += f"📺 **S{file_doc['season']:02}E{file_doc['episode']:02}**\n"
                
                caption += f"\n💾 **Size:** {get_readable_size(file_doc['file_size'])}\n"
                
                # Get poster
                poster_path = details.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                
                # Button
                bot_username = context.bot.username
                kb = [[InlineKeyboardButton("📁 GET FILE", url=f"https://t.me/{bot_username}?start=file_{file_doc['_id']}")]]
                
                # Send
                if poster_url:
                    await context.bot.send_photo(
                        chat_id=UPDATE_CHANNEL,
                        photo=poster_url,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(kb),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await context.bot.send_message(
                        chat_id=UPDATE_CHANNEL,
                        text=caption,
                        reply_markup=InlineKeyboardMarkup(kb),
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                logger.info(f"✅ Posted to update channel: {title}")
        
    except Exception as e:
        logger.error(f"Update channel error: {e}")

# --- FORWARD HANDLER (Manual Indexing) ---
async def forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle forwarded messages for manual channel indexing"""
    msg = update.message
    user_id = msg.from_user.id
    
    if not await is_admin(user_id):
        return
    
    if not msg.forward_from_chat:
        return
    
    forward_chat = msg.forward_from_chat
    
    # Store in context for confirmation
    context.user_data['index_chat_id'] = forward_chat.id
    context.user_data['index_chat_title'] = forward_chat.title or forward_chat.username
    context.user_data['last_message_id'] = msg.forward_from_message_id
    
    text = (
        f"**Do you Want To Index This Channel/Group?**\n\n"
        f"**Chat ID/Username:** `{forward_chat.id}`\n"
        f"**Title:** {forward_chat.title or forward_chat.username}\n"
        f"**Last Message ID:** {msg.forward_from_message_id}\n\n"
        f"ɴᴇᴇᴅ sᴇᴛsᴋɪᴘ 👉🏻 /setskip"
    )
    
    kb = [
        [InlineKeyboardButton("✅ YES", callback_data="idx_yes"),
         InlineKeyboardButton("❌ CLOSE", callback_data="idx_close")]
    ]
    
    reply = await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(auto_delete_message(context, reply.chat_id, reply.message_id, delay=600))

async def index_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle indexing confirmation"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "idx_close":
        await query.message.delete()
        return
    
    elif data == "idx_yes":
        chat_id = context.user_data.get('index_chat_id')
        last_msg_id = context.user_data.get('last_message_id', 100)
        skip = context.user_data.get('skip_messages', 0)
        
        if not chat_id:
            await query.answer("Error: No chat data found", show_alert=True)
            return
        
        await query.edit_message_text("🔄 **Starting indexing...**\n\nThis may take a while.")
        
        # Start indexing in background
        asyncio.create_task(index_channel_task(context, chat_id, last_msg_id, skip, query.message))

async def index_channel_task(context, chat_id, last_msg_id, skip, status_msg):
    """Index channel using Pyrogram"""
    try:
        # Initialize Pyrogram client
        user_client = Client(
            BOT_SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN
        )
        
        await user_client.start()
        
        total_msgs = last_msg_id
        fetched = 0
        saved = 0
        duplicates = 0
        deleted = 0
        non_media = 0
        errors = 0
        
        start_time = time.time()
        batch_size = 200
        current_batch = 0
        total_batches = (total_msgs // batch_size) + 1
        
        for msg_id in range(skip + 1, last_msg_id + 1):
            try:
                msg: PyrogramMessage = await user_client.get_messages(chat_id, msg_id)
                fetched += 1
                
                if msg.empty or msg.service:
                    non_media += 1
                    continue
                
                file_id, unique_id, fname, fsize, ftype = None, None, None, 0, "doc"
                
                if msg.document:
                    file_id = msg.document.file_id
                    unique_id = msg.document.file_unique_id
                    fname = msg.document.file_name
                    fsize = msg.document.file_size
                elif msg.video:
                    file_id = msg.video.file_id
                    unique_id = msg.video.file_unique_id
                    fname = msg.video.file_name or msg.caption or "Video"
                    fsize = msg.video.file_size
                    ftype = "video"
                else:
                    non_media += 1
                    continue
                
                # Check duplicate
                exists = await db.files.find_one({"file_unique_id": unique_id})
                if exists:
                    duplicates += 1
                    continue
                
                # Process
                clean_name = clean_filename(fname)
                category = determine_category(chat_id, clean_name)
                season, episode = extract_metadata(fname)
                quality = extract_quality(fname)
                audio = extract_audio(fname)
                
                file_doc = {
                    "_id": str(hash(unique_id))[:16],
                    "file_id": file_id,
                    "file_unique_id": unique_id,
                    "file_name": clean_name,
                    "file_size": fsize,
                    "file_type": ftype,
                    "category": category,
                    "season": season,
                    "episode": episode,
                    "quality": quality,
                    "audio": audio,
                    "message_id": msg_id,
                    "channel_id": chat_id,
                    "indexed_date": datetime.now()
                }
                
                await db.files.insert_one(file_doc)
                saved += 1
                
            except Exception as e:
                if "deleted" in str(e).lower():
                    deleted += 1
                else:
                    errors += 1
            
            # Update progress every 50 messages
            if fetched % 50 == 0:
                elapsed = time.time() - start_time
                progress = (fetched / total_msgs) * 100
                eta = (elapsed / fetched) * (total_msgs - fetched) if fetched > 0 else 0
                
                current_batch = fetched // batch_size + 1
                bar_length = 10
                filled = int(progress / 10)
                bar = "🟩" * filled + "⬜" * (bar_length - filled)
                
                status_text = (
                    f"📊 **Indexing Progress**\n"
                    f"📦 Batch {current_batch}/{total_batches}\n"
                    f"{bar} {progress:.1f}%\n\n"
                    f"**Total Messages:** {total_msgs}\n"
                    f"**Total Fetched:** {fetched}\n"
                    f"**Saved:** {saved}\n"
                    f"**Duplicates:** {duplicates}\n"
                    f"**Deleted:** {deleted}\n"
                    f"**Non-Media:** {non_media}\n"
                    f"**Errors:** {errors}\n"
                    f"⏱️ **Elapsed:** {int(elapsed)}s\n"
                    f"⏰ **ETA:** {int(eta)}s"
                )
                
                try:
                    await status_msg.edit_text(status_text, parse_mode=ParseMode.MARKDOWN)
                except:
                    pass
            
            await asyncio.sleep(0.1)  # Rate limiting
        
        await user_client.stop()
        
        # Final update
        final_text = (
            f"✅ **Indexing Complete!**\n\n"
            f"**Total Messages:** {total_msgs}\n"
            f"**Fetched:** {fetched}\n"
            f"**Saved:** {saved}\n"
            f"**Duplicates:** {duplicates}\n"
            f"**Deleted:** {deleted}\n"
            f"**Non-Media:** {non_media}\n"
            f"**Errors:** {errors}\n"
            f"⏱️ **Time:** {int(time.time() - start_time)}s"
        )
        
        await status_msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Indexing error: {e}")
        try:
            await status_msg.edit_text(f"❌ **Indexing Failed**\n\nError: {str(e)}")
        except:
            pass

# --- COMMANDS ---
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats command"""
    if not await is_admin(update.effective_user.id):
        return
    
    stats = await get_stats()
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    uptime_seconds = time.time() - psutil.boot_time()
    uptime = str(timedelta(seconds=int(uptime_seconds)))
    
    disk = psutil.disk_usage('/')
    free_storage = disk.free / (1024 * 1024)
    
    text = (
        f"╭────[ 🗃 ᴅᴀᴛᴀʙᴀsᴇ 🗃 ]────⍟\n"
        f"│\n"
        f"├⋟ ᴀʟʟ ᴜsᴇʀs ⋟ {stats['users']}\n"
        f"├⋟ ᴀʟʟ ɢʀᴏᴜᴘs ⋟ {stats['groups']}\n"
        f"├⋟ ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs ⋟ {stats['premium']}\n"
        f"├⋟ ᴀʟʟ ꜰɪʟᴇs ⋟ {stats['files']}\n"
        f"├⋟ ᴜsᴇᴅ sᴛᴏʀᴀɢᴇ ⋟ {stats['used_storage']:.2f} MB\n"
        f"├⋟ ꜰʀᴇᴇ sᴛᴏʀᴀɢᴇ ⋟ {free_storage:.2f} MB\n"
        f"│\n"
        f"├────[ 🤖 ʙᴏᴛ ᴅᴇᴛᴀɪʟs 🤖 ]────⍟\n"
        f"│\n"
        f"├⋟ ᴜᴘᴛɪᴍᴇ ⋟ {uptime}\n"
        f"├⋟ ʀᴀᴍ ⋟ {ram}%\n"
        f"├⋟ ᴄᴘᴜ ⋟ {cpu}%\n"
        f"│\n"
        f"╰─────────────────────⍟"
    )
    
    msg = await update.message.reply_text(text)
    asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))

async def view_members_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all members"""
    if not await is_admin(update.effective_user.id):
        return
    
    users = await db.users.find({}).limit(50).to_list(length=50)
    
    text = "👥 **All Members** (First 50)\n\n"
    for u in users:
        text += f"• **ID:** `{u['user_id']}` - **Name:** {u.get('first_name', 'Unknown')}\n"
    
    msg = await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))

async def setskip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set skip messages for indexing"""
    if not await is_admin(update.effective_user.id):
        return
    
    try:
        skip = int(context.args[0])
        context.user_data['skip_messages'] = skip
        msg = await update.message.reply_text(f"✅ Skip set to: {skip}")
        asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
    except:
        msg = await update.message.reply_text("Usage: /setskip <number>")
        asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))

async def request_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request a file"""
    txt = " ".join(context.args)
    if not txt:
        msg = await update.message.reply_text("Usage: /request <Movie/Series Name>")
        asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
        return
    
    await db.requests.insert_one({
        "user_id": update.effective_user.id,
        "user_name": update.effective_user.first_name,
        "request_text": txt,
        "status": "pending",
        "req_date": datetime.now()
    })
    
    msg = await update.message.reply_text("✅ Request sent to admins!")
    asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))

async def clone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request bot clone"""
    exists = await db.clone_requests.find_one({
        "user_id": update.effective_user.id,
        "status": "pending"
    })
    
    if exists:
        msg = await update.message.reply_text("⏳ You already have a pending request.")
    else:
        await db.clone_requests.insert_one({
            "user_id": update.effective_user.id,
            "user_name": update.effective_user.first_name,
            "status": "pending",
            "req_date": datetime.now()
        })
        msg = await update.message.reply_text("✅ Clone request sent!")
    
    asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View download history"""
    history = await db.history.find({"user_id": update.effective_user.id}).sort("_id", -1).limit(10).to_list(length=10)
    
    if not history:
        msg = await update.message.reply_text("📜 History is empty.")
        asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))
        return
    
    text = "📜 **Your Download History**\n\n"
    for h in history:
        date_str = h["dl_date"].strftime("%Y-%m-%d %H:%M")
        text += f"⏰ {date_str} - {h['file_name'][:30]}...\n"
    
    msg = await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(auto_delete_message(context, msg.chat_id, msg.message_id))

# --- MAIN ---
async def post_init(application):
    """Post initialization"""
    await init_db()
    logger.info("✅ Bot initialized")

async def post_shutdown(application):
    """Cleanup"""
    if mongo_client:
        mongo_client.close()
    logger.info("✅ Bot shutdown")

def main():
    """Main function"""
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("members", view_members_cmd))
    app.add_handler(CommandHandler("setskip", setskip_cmd))
    app.add_handler(CommandHandler("request", request_cmd))
    app.add_handler(CommandHandler("clone", clone_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    
    # Handlers
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_post_handler))
    app.add_handler(MessageHandler(filters.FORWARDED & ~filters.COMMAND, forward_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))
    app.add_handler(CallbackQueryHandler(index_channel_callback, pattern="^idx_"))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🔥 SH ULTRA BOT V2 Started!")
    app.run_polling()

if __name__ == '__main__':
    main()
