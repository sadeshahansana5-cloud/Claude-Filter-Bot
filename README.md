# SH Ultra Telegram Bot V2

A powerful Telegram bot for managing and sharing Movies, Series, and Games with MongoDB, TMDB integration, and auto-indexing features.

## ✨ Features

- 🎬 **Movie & Series Database** - Store and search thousands of files
- 🎮 **Game Library** - Organize PC games
- 🔍 **Advanced Search** - Category-based search with filters
- 📺 **Series Management** - Season/Episode filtering
- 🎨 **TMDB Integration** - Rich movie cards with posters, ratings, and details
- 📢 **Auto Update Channel** - Automatic posting to update channel
- 🗂️ **Channel Indexing** - Index old messages from any channel
- 👥 **User Management** - Premium users, admin panel
- 📊 **Detailed Statistics** - Track users, files, and system stats
- 🔄 **Auto-delete Messages** - Clean chat after 5 minutes
- 💾 **MongoDB Database** - Scalable NoSQL storage
- 🐳 **Docker Ready** - Easy deployment on Render/Railway

## 🚀 Deployment on Render

### Prerequisites

1. **MongoDB Atlas Account** (Free tier available)
   - Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
   - Create a free cluster
   - Get your connection string

2. **Telegram Bot Token**
   - Talk to [@BotFather](https://t.me/BotFather)
   - Create a new bot and get the token

3. **Telegram API Credentials**
   - Go to [my.telegram.org](https://my.telegram.org)
   - Login and go to "API development tools"
   - Get your `API_ID` and `API_HASH`

4. **TMDB API Key** (Optional but recommended)
   - Create account at [TMDB](https://www.themoviedb.org/)
   - Go to Settings → API → Request API Key

### Steps

1. **Fork/Clone this repository**

2. **Create a new Web Service on Render**
   - Go to [Render Dashboard](https://dashboard.render.com/)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Choose "Docker" as runtime

3. **Configure Environment Variables**

   Add these environment variables in Render:

   ```
   BOT_TOKEN=your_bot_token
   OWNER_ID=your_telegram_user_id
   MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
   DB_NAME=sh_bot_db
   API_ID=your_api_id
   API_HASH=your_api_hash
   BOT_SESSION=sh_bot_session
   CH_SINHALA_SUB=-1001234567890
   CH_PC_GAME=-1001234567891
   CH_MOVIE_SERIES=-1001234567892
   UPDATE_CHANNEL=-1001234567893
   AUTHORIZED_GROUP_ID=-1001234567894
   GROUP_LINK=https://t.me/YourGroup
   START_IMAGE=https://telegra.ph/file/abc.jpg
   TMDB_API_KEY=your_tmdb_key
   AUTO_UPDATE_CHANNEL=true
   ```

4. **Deploy**
   - Click "Create Web Service"
   - Wait for deployment to complete

## 🏠 Local Development

### Using Docker Compose

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/sh-bot.git
   cd sh-bot
   ```

2. **Create `.env` file**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Start the bot**
   ```bash
   docker-compose up -d
   ```

4. **View logs**
   ```bash
   docker-compose logs -f bot
   ```

### Manual Setup

1. **Install Python 3.11+**

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   - Copy `.env.example` to `.env`
   - Fill in your credentials

4. **Run the bot**
   ```bash
   python bot.py
   ```

## 📝 Configuration Guide

### Getting Channel IDs

1. **Add bot to your channel** as admin
2. **Forward any message** from the channel to [@userinfobot](https://t.me/userinfobot)
3. Copy the **Chat ID** (it will be negative)

### Getting Your User ID

1. Send any message to [@userinfobot](https://t.me/userinfobot)
2. Copy your **User ID**

### TMDB Configuration

1. Go to [TMDB](https://www.themoviedb.org/signup)
2. Create an account
3. Go to Settings → API
4. Request an API key (choose "Developer" option)
5. Copy the **API Key (v3 auth)**

## 🎮 Bot Commands

### User Commands
- `/start` - Start the bot
- `/request <name>` - Request a missing file
- `/clone` - Request bot source code
- `/history` - View download history

### Admin Commands
- `/stats` - View detailed statistics
- `/members` - View all members
- `/setskip <number>` - Set skip messages for indexing

### Admin Panel
- **Add/Remove Admins** - Manage admin users
- **File Requests** - Approve/Deny user requests
- **Clone Requests** - Share source code
- **Toggle Maintenance** - Enable/Disable bot
- **Toggle Updates** - Turn update channel on/off

## 🔧 Advanced Features

### Channel Indexing

1. **Forward any message** from a channel to the bot (as admin)
2. Bot will ask for confirmation
3. Click **"YES"** to start indexing
4. Use `/setskip <number>` to skip old messages
5. Watch the **progress bar** update in real-time

### Update Channel

When enabled, the bot automatically posts:
- 🎬 Movie posters from TMDB
- ⭐ Ratings and release dates
- 🎭 Genres
- 🎞️ Quality and audio info
- 📁 Direct download button

### Series Organization

Files are automatically organized by:
- **Season** - Extracted from filename (S01, Season 1)
- **Episode** - Extracted from filename (E05, Episode 5)
- **Quality** - 1080p, 720p, etc.
- **Audio** - AAC, DDP5.1, etc.

## 📊 Database Structure

### Collections

- **files** - All indexed files
- **users** - Registered users
- **admins** - Admin users
- **groups** - Authorized groups
- **requests** - User file requests
- **clone_requests** - Source code requests
- **history** - Download history

## 🛡️ Security

- ✅ Admin-only commands protected
- ✅ Group access control
- ✅ Duplicate file prevention
- ✅ Rate limiting on indexing
- ✅ Auto-delete sensitive messages
- ✅ MongoDB authentication

## 🐛 Troubleshooting

### Bot not responding
- Check if bot token is correct
- Verify MongoDB connection
- Check Render logs

### Indexing not working
- Ensure API_ID and API_HASH are correct
- Make sure bot is admin in the channel
- Check if Pyrogram session is created

### TMDB not showing
- Verify TMDB_API_KEY is valid
- Check if movie name matches TMDB database
- Some regional content may not be available

## 📞 Support

For issues and questions:
- Open an issue on GitHub
- Contact: [@YourUsername](https://t.me/yourusername)

## 📜 License

This project is licensed under the MIT License.

## ⚠️ Disclaimer

This bot is for educational purposes only. Please respect copyright laws and use responsibly.

---

**Made with ❤️ by SH BOTS**
