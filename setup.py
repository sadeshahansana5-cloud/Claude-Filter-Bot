#!/usr/bin/env python3
"""
SH Bot Setup Helper
This script helps you configure your bot by generating a .env file
"""

import os
import sys

def print_header():
    print("""
╔═══════════════════════════════════════════╗
║   SH ULTRA BOT V2 - Setup Helper         ║
║   සිංහල Telegram Bot Configuration      ║
╚═══════════════════════════════════════════╝
""")

def get_input(prompt, required=True, default=""):
    while True:
        value = input(f"\n{prompt}")
        if value:
            return value
        elif not required and not value:
            return default
        else:
            print("❌ This field is required!")

def main():
    print_header()
    
    print("\n📝 Let's configure your bot step by step...\n")
    
    # Bot Token
    print("=" * 50)
    print("1️⃣  TELEGRAM BOT TOKEN")
    print("=" * 50)
    print("Get this from @BotFather on Telegram")
    bot_token = get_input("Enter your Bot Token: ")
    
    # Owner ID
    print("\n" + "=" * 50)
    print("2️⃣  OWNER ID")
    print("=" * 50)
    print("Get this from @userinfobot on Telegram")
    owner_id = get_input("Enter your Telegram User ID: ")
    
    # MongoDB
    print("\n" + "=" * 50)
    print("3️⃣  MONGODB CONNECTION")
    print("=" * 50)
    print("Get this from MongoDB Atlas (mongodb+srv://...)")
    mongodb_uri = get_input("Enter MongoDB URI: ")
    db_name = get_input("Enter Database Name (default: sh_bot_db): ", False, "sh_bot_db")
    
    # Pyrogram
    print("\n" + "=" * 50)
    print("4️⃣  PYROGRAM CREDENTIALS")
    print("=" * 50)
    print("Get these from https://my.telegram.org")
    api_id = get_input("Enter API ID: ")
    api_hash = get_input("Enter API Hash: ")
    
    # Channels
    print("\n" + "=" * 50)
    print("5️⃣  CHANNEL CONFIGURATION")
    print("=" * 50)
    print("Forward any message from channel to @userinfobot to get ID")
    print("(IDs should be negative numbers like -1001234567890)")
    
    ch_sinhala = get_input("Sinhala Sub Channel ID: ")
    ch_game = get_input("PC Game Channel ID: ")
    ch_movie = get_input("Movie/Series Channel ID: ")
    update_channel = get_input("Update Channel ID (where bot posts): ")
    auth_group = get_input("Authorized Group ID (where users search): ")
    
    # Links
    print("\n" + "=" * 50)
    print("6️⃣  LINKS & IMAGES")
    print("=" * 50)
    group_link = get_input("Group Invite Link (https://t.me/...): ")
    start_image = get_input("Start Image URL (https://telegra.ph/file/...): ", False, "https://telegra.ph/file/sample.jpg")
    
    # TMDB
    print("\n" + "=" * 50)
    print("7️⃣  TMDB API (Optional)")
    print("=" * 50)
    print("Get this from https://www.themoviedb.org/settings/api")
    tmdb_key = get_input("Enter TMDB API Key (or press Enter to skip): ", False, "")
    
    # Auto Update
    print("\n" + "=" * 50)
    print("8️⃣  FEATURES")
    print("=" * 50)
    auto_update = get_input("Enable Auto Update Channel? (yes/no): ", False, "yes")
    auto_update = "true" if auto_update.lower() in ["yes", "y", "true"] else "false"
    
    # Generate .env file
    env_content = f"""# Bot Configuration
BOT_TOKEN={bot_token}
OWNER_ID={owner_id}

# MongoDB Configuration
MONGODB_URI={mongodb_uri}
DB_NAME={db_name}

# Pyrogram Configuration
API_ID={api_id}
API_HASH={api_hash}
BOT_SESSION=sh_bot_session

# Channel IDs
CH_SINHALA_SUB={ch_sinhala}
CH_PC_GAME={ch_game}
CH_MOVIE_SERIES={ch_movie}
UPDATE_CHANNEL={update_channel}
AUTHORIZED_GROUP_ID={auth_group}

# Links and Images
GROUP_LINK={group_link}
START_IMAGE={start_image}

# TMDB API
TMDB_API_KEY={tmdb_key}

# Features
AUTO_UPDATE_CHANNEL={auto_update}
"""
    
    # Save to file
    with open(".env", "w") as f:
        f.write(env_content)
    
    print("\n" + "=" * 50)
    print("✅ Configuration Complete!")
    print("=" * 50)
    print("\n📁 .env file has been created successfully!")
    print("\n🚀 Next Steps:")
    print("   1. Review your .env file")
    print("   2. Deploy to Render using Docker")
    print("   3. Or run locally: python bot.py")
    print("\n📖 Check README.md for detailed instructions")
    print("\n🇱🇰 සිංහල උපදෙස් සඳහා SETUP_GUIDE.md බලන්න\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
