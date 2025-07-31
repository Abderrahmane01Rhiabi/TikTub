# 🔐 Security Setup Guide for TikTub

## ⚠️ IMPORTANT SECURITY NOTICE

This project has been configured to protect your sensitive information. Follow these steps carefully:

## 🔑 Required Setup Steps

### 1. Copy Configuration Templates
```bash
# Copy the example config file
cp config.yaml.example config.yaml

# Copy the environment template
cp .env.example .env
```

### 2. Add Your API Keys

#### For Gemini AI (Recommended - Free tier available):
1. Visit: https://aistudio.google.com/app/apikey
2. Create your free API key
3. Edit `.env` and add: `GEMINI_API_KEY=your_actual_key_here`

#### For OpenAI (Optional):
1. Visit: https://platform.openai.com/api-keys
2. Create your API key
3. Edit `.env` and add: `OPENAI_API_KEY=your_actual_key_here`

### 3. YouTube Credentials Setup
1. Follow the main README instructions for YouTube API setup
2. Download your `credentials.json` from Google Cloud Console
3. Place it in the project root directory

## 🚫 Files That Are Automatically Ignored

The following files are automatically excluded from git commits:
- `config.yaml` - Your configuration with API keys
- `credentials.json` - YouTube API credentials
- `token.json` - YouTube authentication tokens
- `.env` - Environment variables with API keys
- `database/` - Local video database
- `processed_videos/` - Video files
- `upload_schedule.json` - Your upload schedules
- `channels/*/credentials.json` - Multi-channel credentials
- `channels/*/token.json` - Multi-channel tokens

## ✅ Safe to Commit

These template files are safe and should be committed:
- `config.yaml.example` - Template configuration
- `.env.example` - Environment template
- `urls.txt.example` - Example URLs file
- `sample_ai_result.json` - Example AI output

## 🛡️ Security Best Practices

1. **Never commit sensitive files** - They're already in .gitignore
2. **Use strong API keys** - Keep them secret and rotate regularly
3. **Don't share your credentials** - Each user should have their own
4. **Keep backups** - But store them securely, not in version control

## 🔍 If You Accidentally Committed Sensitive Data

If you accidentally committed sensitive information:

```bash
# Remove from git but keep local copy
git rm --cached filename

# Or remove from entire git history (DANGEROUS - use carefully)
git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch filename' --prune-empty --tag-name-filter cat -- --all
```

## 📞 Need Help?

If you have security concerns or questions:
1. Check the main README.md for setup instructions
2. Create an issue on GitHub (don't include sensitive data!)
3. Review the .gitignore file to see what's excluded
