# 🤖 Social Content Bot

A Python bot that automatically generates social media post suggestions (Twitter/X and LinkedIn) from your Reddit upvotes and WordPress blog posts, then delivers them via email.

## ✨ Features

- **Reddit Integration**: Fetches your upvoted posts from Reddit
- **WordPress Integration**: Retrieves your blog posts via REST API
- **AI-Powered Content Generation**: Uses OpenAI-compatible APIs to generate engaging social media posts
- **Email Delivery**: Sends a beautifully formatted HTML digest email
- **Multi-language Support**: Generate content in your preferred language
- **Parallel Processing**: Async API calls for faster content generation
- **Retry Logic**: Automatic retry with exponential backoff for failed requests
- **Comprehensive Logging**: Rotating log files for debugging and monitoring
- **Fully Configurable**: Extensive environment variable configuration

## 📋 Prerequisites

- Python 3.9 or higher
- Reddit account with API access
- WordPress site with REST API enabled
- OpenAI API key (or compatible API)
- SMTP server for email (e.g., Gmail)

## 🚀 Quick Start

### 1. Clone and Install

```bash
cd social-content-bot
uv pip install -e .
```

### 2. Configure Environment

Copy the example environment file and edit it with your credentials:

```bash
cp .env.example .env
nano .env
```

### 3. Run the Bot

```bash
python main.py
```

## ⚙️ Configuration

### Reddit API Setup

1. Go to [Reddit App Preferences](https://www.reddit.com/prefs/apps)
2. Click "Create App" or "Create Another App"
3. Choose **"script"** as the app type
4. Fill in the details:
   - Name: `SocialContentBot` (or any name you prefer)
   - Redirect URI: `http://localhost:8080` (not used for script apps)
5. Note your credentials:
   - **Client ID**: Under the app name (looks like `abc123xyz`)
   - **Client Secret**: Labeled as "secret"

Add to `.env`:

```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=SocialContentBot/1.0 by YOUR_USERNAME
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password
```

### WordPress Configuration

For public sites, you only need the site URL. For private sites or to access draft posts:

1. Log into WordPress Admin
2. Go to **Users → Profile**
3. Scroll to **Application Passwords**
4. Enter a name (e.g., "Social Content Bot") and click "Add New Application Password"
5. Copy the generated password

Add to `.env`:

```env
WORDPRESS_SITE_URL=https://yourblog.com
WORDPRESS_USERNAME=your_username
WORDPRESS_APP_PASSWORD=your_app_password
```

### OpenAI API Configuration

Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys).

Add to `.env`:

```env
OPENAI_API_KEY=sk-your-api-key-here
```

**Alternative**: You can use any OpenAI-compatible API by setting:

```env
OPENAI_API_BASE=https://your-api-endpoint/v1
OPENAI_API_KEY=your-api-key
```

### Email (SMTP) Configuration

#### Gmail Setup

1. Enable 2-Factor Authentication on your Google Account
2. Go to [Google Account Security](https://myaccount.google.com/security)
3. Search for "App Passwords" and create one
4. Use the generated 16-character password

Add to `.env`:

```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=recipient@example.com
```

#### Other Email Providers

| Provider | SMTP Server | Port |
|----------|-------------|------|
| Outlook/Hotmail | smtp-mail.outlook.com | 587 |
| Yahoo | smtp.mail.yahoo.com | 587 |
| Fastmail | smtp.fastmail.com | 587 |

## 📖 Usage

### Basic Usage

```bash
# Run with default settings
python main.py

# Dry run (don't send email, just display suggestions)
python main.py --dry-run

# Only process Reddit content
python main.py --skip-wordpress

# Only process WordPress content
python main.py --skip-reddit
```

### Advanced Options

```bash
# Custom Reddit limit
python main.py --reddit-limit 20

# Generate more suggestions per item
python main.py --posts-per-item 3

# Generate in different language
python main.py --language it

# Save results to JSON
python main.py --output results.json

# Use custom env file
python main.py --env-file /path/to/.env

# Use synchronous mode (slower, for debugging)
python main.py --sync

# Custom log level
python main.py --log-level DEBUG
```

### Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--reddit-limit` | 10 | Max Reddit upvotes to fetch |
| `--posts-per-item` | 2 | Suggestions per content item |
| `--language` | en | Language for generated content |
| `--skip-reddit` | false | Skip Reddit processing |
| `--skip-wordpress` | false | Skip WordPress processing |
| `--dry-run` | false | Don't send email |
| `--output, -o` | - | Save results to JSON file |
| `--env-file` | .env | Path to environment file |
| `--sync` | false | Use synchronous API calls |
| `--log-level` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
