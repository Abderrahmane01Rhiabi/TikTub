# 🎬 TikTub - AI-Powered TikTok to YouTube Automation

**TikTub** is an intelligent automation system that downloads TikTok videos, processes them for YouTube Shorts format, and uploads them with **AI-generated content optimization** and smart scheduling.

## 🚀 What This App Does

### 🌟 Core Features:
- ⬇️ **Download TikTok Videos** - Automatically downloads videos using URLs
- 🎨 **Smart Background Processing** - Converts vertical TikTok videos to YouTube Shorts 9:16 format
- 🤖 **AI Content Generation** - **NEW!** Multi-provider AI system with advanced content detection
- 🎯 **Smart Content Detection** - **NEW!** Detects anime, games, movies, artists, and brands
- 📺 **Multi-Channel Support** - **NEW!** Upload to different YouTube channels with ease
- ⏰ **Smart Scheduling** - Uploads at optimal times for maximum engagement
- 📊 **Batch Processing** - Handle multiple videos at once with AI optimization
- 🔄 **Quota Management** - Manages YouTube API limits intelligently
- 💡 **Three-Tier AI System** - Gemini AI → OpenAI → Local AI fallback

### 🎯 AI-Powered Content Optimization:
- **Viral Title Generation** - AI creates click-worthy, SEO-optimized titles
- **Smart Descriptions** - YouTube-optimized descriptions with trending hashtags
- **Intelligent Tagging** - Context-aware tags for maximum discoverability
- **Content Recognition** - Detects specific anime series, games, movies, artists
- **Audience Targeting** - Generates content tailored to specific demographics

### Perfect For:
- Content creators repurposing TikTok content
- Social media managers seeking AI optimization
- Anime, gaming, and entertainment channels
- Multi-channel content creators and networks
- Anyone wanting intelligent TikTok → YouTube automation

---

## 📺 Multi-Channel Support (NEW!)

### **Upload to Multiple YouTube Channels**
**TikTub now supports unlimited YouTube channels!** Perfect for:
- 🎮 **Separate gaming channel** for gaming content
- 📺 **Dedicated anime channel** for anime clips  
- 🎵 **Music channel** for music-related videos
- 🎭 **Main channel** for general entertainment

### **Channel Management Features**
```
📺 Channel Selection Menu:
├── 🏠 Main Channel (your original setup)
├── 🎮 Gaming Channel  
├── 📺 Anime Channel
└── 🎵 Music Channel
```

### **Quick Setup**
```bash
# Setup multi-channel support
python setup_channels.py

# Add your channels
1. Add new channel → Gaming Channel
2. Download OAuth credentials for each channel
3. Upload with channel selection
```

### **How It Works**
- **Backward Compatible**: Your current setup keeps working
- **Individual Credentials**: Each channel has separate OAuth
- **Smart Selection**: Choose channel during upload
- **Zero Conflicts**: No interference between channels

---

## 🤖 AI Features Overview

### **Multi-Provider AI System**
```
🥇 Gemini AI (Primary) - $0.075/1M tokens - Excellent quality
🥈 OpenAI GPT-4 (Backup) - $10-30/1M tokens - Premium quality  
🥉 Local AI (Fallback) - Free - Basic quality
```

### **Advanced Content Detection**
- 📺 **Anime & Manga**: Naruto, One Piece, Attack on Titan, Dragon Ball
- 🎮 **Gaming**: Fortnite, Minecraft, GTA, Valorant, Pokemon
- 🎬 **Movies**: Marvel, DC, Fast & Furious, Star Wars
- 🎵 **Music & Artists**: BTS, Taylor Swift, K-pop, Hip-hop
- 🏷️ **Brands & Logos**: Nike, Apple, McDonald's, Samsung

### **Smart Content Generation Examples**
```
Input: Gaming video with Fortnite content
AI Output:
├── Title: "This Fortnite Play Broke The Game 🎮"
├── Description: "Epic Fortnite moment! 🔥 #Fortnite #Gaming #Epic"
└── Tags: ["fortnite", "gaming", "battle royale", "epic", "viral"]

Input: Anime video with Dragon Ball content  
AI Output:
├── Title: "POV: Goku Goes Ultra Instinct 🔥"
├── Description: "Goku's power is unreal! ⚡ #DragonBall #Anime #Goku"
└── Tags: ["dragonball", "goku", "anime", "supersaiyan", "manga"]
```

---

## 📋 Prerequisites

### 1. Python Environment
```bash
pip install -r requirements.txt
```

### 2. AI API Setup (Choose One or Both)

#### **Option A: Gemini AI (Recommended - Cheap & Effective)**
```bash
python setup_gemini.py
```
- Cost: ~$0.01 per video analysis
- Free tier: 1,500 requests/day
- Get API key: [Google AI Studio](https://makersuite.google.com/app/apikey)

#### **Option B: OpenAI (Premium Quality)**
```bash
python setup_openai.py  
```
- Cost: ~$0.03-0.05 per video analysis
- Premium content detection
- Get API key: [OpenAI Platform](https://platform.openai.com/api-keys)

### 3. YouTube API Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable YouTube Data API v3
4. Create credentials (OAuth 2.0 Client ID)
5. Download `credentials.json` and place it in the project root

### 4. Background Images
- Add background images to `backgrounds/` folder
- Recommended: 1080x1920 resolution (9:16 aspect ratio)
- Supported formats: JPG, PNG

---

## 🎯 Quick Start Guide

### Method 1: AI-Enhanced Single Video Test
```bash
# Test with AI content generation
python test3_script.py
```

### Method 2: AI-Powered Batch Processing (Recommended)
```bash
# Process multiple videos with AI optimization
python batch_processor.py
```

### Method 3: Legacy Processing
```bash
# Basic processing without AI
python script.py
```

---

## 📁 Project Structure

```
TikTub/
├── 📄 Core Scripts
│   ├── batch_processor.py     # 🎯 Main control center with AI
│   ├── test3_script.py        # 🤖 AI-enhanced video processor  
│   ├── script.py              # 📜 Legacy main script
│   └── youtube_uploader.py    # 📤 YouTube upload handler
│
├── 🤖 AI Intelligence Layer
│   ├── ai_tags_generator.py   # 🧠 Multi-provider AI coordinator
│   ├── gemini_ai_generator.py # 🔷 Google Gemini AI integration
│   ├── openai_ai_generator.py # 🔶 OpenAI GPT-4 Vision integration
│   ├── setup_gemini.py        # ⚙️ Gemini API setup assistant
│   └── setup_openai.py        # ⚙️ OpenAI API setup assistant
│
├── � Multi-Channel System (NEW!)
│   ├── channel_manager.py     # 🎛️ Channel management core
│   ├── setup_channels.py      # 🏗️ Interactive channel setup wizard
│   └── channels/              # 📁 Channel credentials storage
│       ├── default/           # 🏠 Your main channel
│       ├── gaming_channel/    # 🎮 Gaming content channel
│       └── anime_channel/     # 📺 Anime content channel
│
├── �📊 Data Management
│   ├── url_manager.py         # 📋 URL batch management
│   ├── youtube_scheduler.py   # ⏰ Smart upload scheduling
│   └── database/              # 💾 Processing databases
│       ├── videos_status.json
│       ├── upload_schedule.json
│       └── youtube_quota.json
│
├── ⚙️ Configuration
│   ├── config.yaml           # 🔧 Main configuration
│   ├── credentials.json      # 🔑 YouTube API credentials
│   ├── token.json           # 🎟️ OAuth tokens
│   ├── .env                 # � AI API keys (create this)
│   └── requirements.txt     # 📦 Python dependencies
│
├── 📥 Input & Output
│   ├── urls_input/          # 📋 TikTok URL batches
│   ├── processed_videos/    # 🎬 Processed video output
│   ├── temp/               # 🗂️ Temporary processing files
│   └── backgrounds/        # 🎨 Background images
```
---

## � How to Use TikTub

### Step 1: Setup AI (Choose Your Preference)

#### **Quick Setup - Gemini AI (Recommended)**
```bash
python setup_gemini.py
```
- **Cost**: ~$0.01 per video (very cheap!)
- **Quality**: Excellent content detection
- **Free Tier**: 1,500 requests/day
- **Best For**: Most users, cost-effective automation

#### **Premium Setup - OpenAI (Optional)**
```bash
python setup_openai.py
```
- **Cost**: ~$0.03-0.05 per video 
- **Quality**: Premium AI analysis
- **Best For**: High-quality content, critical projects

### Step 2: Prepare Your URLs
Create/edit `urls_input/batch1.txt` with your TikTok URLs:

#### **Simple Format (Beginner)**:
```
https://www.tiktok.com/@username/video/1234567890
https://www.tiktok.com/@username/video/0987654321
```

#### **Advanced Format (Pro Users)**:
```
URL | Custom Title | Background | Priority | Description
https://www.tiktok.com/@anime_clips/video/123 | Epic Anime Moment | random | high | Amazing anime compilation
https://www.tiktok.com/@gaming_pro/video/456 | Insane Gaming Play | blur | normal | Epic gaming highlights
```

**Field Descriptions:**
- **URL**: TikTok video URL
- **Custom Title**: Base title (AI will optimize it)
- **Background**: `random`, `blur`, `gradient`, `solid`, `specific`
- **Priority**: `high`, `normal`, `low` (processing order)
- **Description**: Base description (AI will enhance it)

### Step 3: Configure Settings (Optional)
Edit `config.yaml` to customize behavior:
```yaml
processing:
  batch_size: 5
  delay_between_videos: 30

youtube:
  auto_upload: false          # Set true for automatic upload
  manual_approval: true       # Ask before each upload
  
ai_tags:
  enabled: true              # Enable AI tag generation
  max_tags: 15
```

### Step 4: Run TikTub

#### **🧪 Testing Mode (No Upload)**
```bash
# Test with AI content generation
python test3_script.py
```
**What it does:**
- Downloads TikTok video
- Applies AI content analysis
- Generates optimized titles, descriptions, tags
- Processes video with background
- **No YouTube upload** (safe for testing)

#### **🚀 Full Automation Mode**
```bash
# Complete AI-powered workflow
python batch_processor.py
```
**What it does:**
- Processes all URLs in batch files
- AI analyzes each video for content
- Generates viral titles and descriptions
- Schedules uploads at optimal times
- Uploads to YouTube with AI-generated metadata

#### **📝 Single Video Mode**
```bash
# Process one video manually
python script.py
```

---

## 🎮 Real Usage Examples

### Example 1: **Gaming Content Detection**
```bash
Input URL: https://www.tiktok.com/@gamer/video/fortnite-clip
```
**AI Detection Results:**
```
🔍 Content Analysis:
├── Category: Gaming
├── Game Detected: Fortnite
├── Content Type: Epic gameplay moment
└── Viral Potential: 8.5/10

🎯 AI-Generated Content:
├── Title: "This Fortnite Play Broke The Game 🎮"
├── Description: "Epic Victory Royale moment! 🔥 #Fortnite #Gaming #EpicGames"
└── Tags: ["fortnite", "gaming", "battle royale", "victory royale", "epic"]
```

### Example 2: **Anime Content Detection**
```bash
Input URL: https://www.tiktok.com/@anime_fan/video/dragon-ball-clip
```
**AI Detection Results:**
```
🔍 Content Analysis:
├── Category: Anime
├── Series Detected: Dragon Ball Z
├── Character: Goku
└── Viral Potential: 9.2/10

🎯 AI-Generated Content:
├── Title: "POV: Goku Goes Ultra Instinct 🔥"
├── Description: "Goku's power is unreal! ⚡ #DragonBall #Anime #Goku #UltraInstinct"
└── Tags: ["dragonball", "goku", "anime", "supersaiyan", "ultra instinct"]
```

### Example 3: **Batch Processing Results**
### Example 3: **Batch Processing Results**
```bash
🚀 BATCH PROCESSOR - AI-Powered Results
=======================================================
📊 Processing Summary:
├── 5 videos processed
├── AI Provider: Gemini → Local fallback
├── Content Detection: 3 anime, 1 gaming, 1 entertainment
├── Average Optimization Score: 87%
└── Total Processing Time: 12 minutes

🎯 AI Content Generated:
├── Video 1: "Naruto's Most INSANE Jutsu 🔥" (Anime detected)
├── Video 2: "This Minecraft Build Is Impossible 🏗️" (Gaming detected)  
├── Video 3: "You Won't Believe This Happens 🤯" (General entertainment)
├── Video 4: "Attack on Titan Fans Will Cry 😭" (Anime detected)
└── Video 5: "One Piece Theory CONFIRMED 🏴‍☠️" (Anime detected)
```

---

## 💡 AI System Details

### **Provider Comparison**
| Feature | Gemini AI | OpenAI | Local AI |
|---------|-----------|--------|----------|
| **Cost per Video** | ~$0.01 | ~$0.03-0.05 | Free |
| **Content Detection** | ✅ Excellent | ✅ Premium | ❌ Basic |
| **Anime Recognition** | ✅ Very Good | ✅ Excellent | ⚠️ Keywords only |
| **Gaming Detection** | ✅ Very Good | ✅ Excellent | ⚠️ Keywords only |
| **Movie Recognition** | ✅ Good | ✅ Excellent | ❌ None |
| **Speed** | ⚡ Fast | ⚡ Fast | ⚡ Instant |
| **Reliability** | ⚠️ Sometimes overloaded | ✅ Very reliable | ✅ Always works |

### **Smart Fallback System**
```
🔄 AI Provider Fallback Chain:
1. Try Gemini AI (cheapest, excellent quality)
   ↓ If fails (overloaded/no credits)
2. Try OpenAI (premium, most reliable)  
   ↓ If fails (no credits/quota exceeded)
3. Use Local AI (always works, basic quality)
   ✅ Never fails - always generates content!
```

### **Content Categories Detected**
- 📺 **Anime & Manga**: Series names, character recognition, episode references
- 🎮 **Gaming**: Game titles, character names, gameplay types
- 🎬 **Movies & TV**: Franchise detection, character recognition
- 🎵 **Music & Artists**: Artist names, song recognition, genre classification
- 🏷️ **Brands & Products**: Logo detection, product recognition
- 🎭 **Entertainment**: Comedy, dance, viral trends, memes

---

## ⚙️ Configuration Options

### **AI Provider Preferences**
Edit `ai_tags_generator.py` to set preferred provider:
```python
# Initialize with preferred provider
ai_generator = AITagsGenerator(preferred_provider="gemini")  # or "openai"
```

### **config.yaml Settings**
```yaml
processing:
  batch_size: 5                    # Videos per batch
  delay_between_videos: 30         # Seconds between processing
  max_duration: 60                 # Max video length (seconds)
  
ai_settings:
  preferred_provider: "gemini"     # "gemini", "openai", or "local"
  enable_content_detection: true   # Enable specific content detection
  confidence_threshold: 0.7        # Minimum AI confidence for results
  
youtube:
  auto_upload: false              # Set true for automatic upload
  manual_approval: true           # Ask before each upload
  privacy_status: "private"       # "private", "unlisted", "public"
  
scheduling:
  optimal_times: ["18:00", "20:00", "22:00"]  # Best upload times
  timezone: "UTC"
  days_ahead: 7                   # Schedule up to 7 days in advance
```

---

## 🛠️ Troubleshooting

### **Common Issues & Solutions**

#### **AI API Issues**
```bash
❌ Gemini API error: 503 - Model overloaded
```
**Solution**: Gemini free tier gets overloaded. System automatically falls back to Local AI.

```bash
❌ OpenAI API error: 429 - Quota exceeded  
```
**Solution**: Add credits to your OpenAI account or wait for quota reset.

#### **Video Processing Issues**
```bash
❌ Video download failed
```
**Solutions**: 
- Check if TikTok URL is valid and public
- Update yt-dlp: `pip install --upgrade yt-dlp`
- Try different video URL

#### **YouTube Upload Issues**
```bash
❌ YouTube quota exceeded
```
**Solutions**:
- Wait 24 hours for quota reset
- Use scheduling to spread uploads
- Apply for higher quota limits

### **Performance Optimization**
- **For Speed**: Use Local AI only (instant generation)
- **For Quality**: Use OpenAI (premium detection)  
- **For Cost**: Use Gemini AI (best balance)
- **For Reliability**: Enable all three (automatic fallback)

---

## 📊 System Architecture

### **Processing Flow**
```
📱 TikTok URL Input
    ↓
⬇️ Video Download (yt-dlp)
    ↓  
🤖 AI Content Analysis
├── 🔷 Gemini AI (Primary)
├── 🔶 OpenAI (Backup)  
└── 🧠 Local AI (Fallback)
    ↓
🎬 Video Processing
├── Background application
├── Format conversion (9:16)
└── Quality optimization
    ↓
📝 Metadata Generation
├── AI-optimized titles
├── SEO descriptions  
└── Targeted tags
    ↓
📤 YouTube Upload (Optional)
├── Smart scheduling
├── Quota management
└── Success tracking
```

### **File Dependencies**
```
batch_processor.py (Main Controller)
├── test3_script.py (Video Processing)
│   └── ai_tags_generator.py (AI Coordinator)
│       ├── gemini_ai_generator.py (Gemini API)
│       ├── openai_ai_generator.py (OpenAI API)  
│       └── [Local AI Templates]
├── url_manager.py (Batch Management)
├── youtube_scheduler.py (Upload Scheduling)
└── youtube_uploader.py (YouTube API)
```

---

## 🚀 Advanced Features

### **Smart Scheduling**
- Analyzes your audience timezone
- Schedules uploads for maximum engagement
- Avoids API quota conflicts
- Spreads uploads across optimal time slots

### **Quota Management**  
- Tracks YouTube API usage
- Prevents quota exceeded errors
- Automatically schedules when quotas reset
- Shows usage statistics and warnings

### **Content Optimization**
- AI analyzes video content and generates context-aware metadata
- Detects trending topics and incorporates them
- Optimizes for YouTube Shorts algorithm
- Generates multiple title variations for A/B testing

### **Batch Intelligence**
- Prioritizes high-quality content first
- Groups similar content for consistent branding
- Balances different content types in upload schedule
- Provides processing analytics and insights

---

## 📈 Success Tips

### **For Maximum Views**
1. **Use AI Content Detection**: Let AI identify specific games/anime for targeted titles
2. **Upload During Peak Hours**: Use the smart scheduler for optimal timing
3. **Mix Content Types**: Balance anime, gaming, entertainment for diverse audience
4. **Monitor Performance**: Track which AI-generated titles perform best

### **For Cost Efficiency**  
1. **Start with Gemini**: Use the cheapest AI option first
2. **Batch Processing**: Process multiple videos together to reduce API calls
3. **Local AI Backup**: Always have free fallback for uninterrupted processing
4. **Monitor Usage**: Track AI API costs and set monthly limits

### **For Content Quality**
1. **Use OpenAI for Important Videos**: Premium AI for your best content
2. **Review AI Suggestions**: Always check generated titles and descriptions
3. **Custom Backgrounds**: Use specific backgrounds that match content themes
4. **Test Different Prompts**: Experiment with custom prompts for better results

---

## 🔗 Useful Links

- **Gemini AI**: [Google AI Studio](https://makersuite.google.com/app/apikey)
- **OpenAI API**: [OpenAI Platform](https://platform.openai.com/api-keys)
- **YouTube API**: [Google Cloud Console](https://console.cloud.google.com/)
- **TikTok Downloader**: [yt-dlp Documentation](https://github.com/yt-dlp/yt-dlp)

---

## 📄 License

This project is open source. Feel free to modify and distribute according to your needs.

## 🤝 Contributing

Contributions are welcome! Areas for improvement:
- Additional AI providers integration  
- Enhanced content detection algorithms
- Better scheduling optimization
- UI/Web interface development

---

**🚀 Ready to automate your TikTok to YouTube workflow with AI? Start with `python batch_processor.py` and let the AI do the work!**
python test_script.py
# Check results in processed_videos/ folder
```

### Example 2: Batch Processing with Manual Approval
```bash
# Processes all URLs in batch1.txt
python batch_processor.py
# System will ask permission before each upload
```

### Example 3: Fully Automated
1. Set `auto_upload: true` in `config.yaml`
2. Run: `python batch_processor.py`
3. System handles everything automatically

---

## 📊 Features Breakdown

### 📝 URL Input Formats
**Simple Format**: Just paste TikTok URLs (one per line)
```
https://www.tiktok.com/@user/video/123456789
```

**Advanced Format**: Full control with pipe-separated metadata
```
URL | Title | Background | Priority | Description
```
- **Background Options**: `random`, `blur`, `gradient`, `solid`, `specific`
- **Priority Levels**: `high` (first), `normal`, `low` (last)
- **Custom Titles & Descriptions**: Enhanced by AI for better YouTube SEO

### 🎨 Video Processing
- Downloads TikTok videos in best quality
- Adds background to fit YouTube Shorts format (9:16)
- Multiple background styles: blur, gradient, solid color
- Maintains original video quality

### 🤖 AI Tag Generation
- Analyzes video title and content
- Generates trending and relevant tags
- Includes seasonal and category-specific tags
- Maximizes discoverability

### ⏰ Smart Scheduling
- Uploads during peak engagement hours
- Manages YouTube API quotas
- Prevents rate limiting
- Optimal timing: 8-10am, 12-2pm, 6-10pm GMT

### 📋 Batch Management
- Process multiple videos in sequence
- Status tracking and error handling
- Resume interrupted processes
- Detailed logging

---

## 🛡️ Important Notes

### ⚠️ Legal Compliance
- Only use videos you own or have permission to use
- Respect TikTok's Terms of Service
- Give proper attribution when required

### 🔒 Security
- Never share your `credentials.json` file
- Keep `token.json` private
- Use environment variables for sensitive data in production

### 📈 Best Practices
- Start with 1-2 videos for testing
- Use high-quality background images
- Monitor YouTube analytics for optimal posting times
- Keep video titles under 100 characters

---

## 🚨 Troubleshooting

### Common Issues:

**"No module named 'yt_dlp'"**
```bash
pip install -r requirements.txt
```

**"YouTube API quota exceeded"**
- Wait 24 hours for quota reset
- Check `database/youtube_quota.json` for current usage

**"TikTok video not accessible"**
- Ensure video is public
- Check if URL is correct
- Some regions may block certain videos

**"Background images not found"**
- Add images to `backgrounds/` folder
- Supported formats: JPG, PNG
- Recommended resolution: 1080x1920

---

## 🔄 Workflow Summary

1. **Input** → Add TikTok URLs to `urls_input/batch1.txt`
2. **Process** → Run `python batch_processor.py`
3. **AI Magic** → System generates tags and schedules uploads
4. **Output** → Videos uploaded to YouTube as Shorts
5. **Track** → Monitor progress in `database/` files

---

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Review log files in project directory
3. Ensure all dependencies are installed
4. Verify YouTube API credentials are correct

---

## 🧪 Tests automatiques

La suite de tests est dans `tests/` (publication, quota YouTube, planning, API web). Chaque test tourne dans un dossier temporaire : jamais sur ta vraie base, tes chaînes ou tes clés, et sans aucun appel à YouTube, Gemini, OpenAI ou ElevenLabs.

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt   # une seule fois (installe pytest)
python -m pytest
```

Les anciens fichiers `test_*.py` à la racine sont des scripts manuels, pas des tests automatiques : pytest les ignore volontairement.
