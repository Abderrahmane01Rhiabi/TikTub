# 🎬 TikTub - TikTok to YouTube Shorts Automation

**TikTub** is an intelligent automation system that downloads TikTok videos, processes them for YouTube Shorts format, and uploads them with AI-generated tags and smart scheduling.

## 🚀 What This App Does

### Core Features:
- ⬇️ **Download TikTok Videos** - Automatically downloads videos using URLs
- 🎨 **Add Backgrounds** - Converts vertical TikTok videos to YouTube Shorts 9:16 format
- 🤖 **AI Tag Generation** - Automatically generates relevant tags for better discoverability
- ⏰ **Smart Scheduling** - Uploads at optimal times for maximum engagement
- 📊 **Batch Processing** - Handle multiple videos at once
- 🔄 **Quota Management** - Manages YouTube API limits intelligently

### Perfect For:
- Content creators repurposing TikTok content
- Social media managers
- Anyone wanting to automate TikTok → YouTube workflow

---

## 📋 Prerequisites

### 1. Python Packages
```bash
pip install -r requirements.txt
```

### 2. YouTube API Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable YouTube Data API v3
4. Create credentials (OAuth 2.0 Client ID)
5. Download `credentials.json` and place it in the project root

### 3. Background Images
- Add background images to `backgrounds/` folder
- Recommended: 1080x1920 resolution (9:16 aspect ratio)
- Supported formats: JPG, PNG

---

## 🎯 Quick Start Guide

### Method 1: Single Video Test
```bash
# Test with one video
python test_script.py
```

### Method 2: Batch Processing (Recommended)
```bash
# Process multiple videos with scheduling
python batch_processor.py
```

### Method 3: Original Script
```bash
# Simple processing
python script.py
```

---

## 📁 Project Structure

```
TikTub/
├── 📄 Core Scripts
│   ├── script.py              # Original main script
│   ├── batch_processor.py     # Advanced batch processing
│   ├── test_script.py         # Core video processor
│   └── youtube_uploader.py    # YouTube upload handler
│
├── 🤖 AI & Automation
│   ├── ai_tags_generator.py   # AI-powered tag generation
│   └── scheduler.py           # Smart upload scheduling
│
├── ⚙️ Configuration
│   ├── config.yaml           # Main configuration
│   ├── credentials.json      # YouTube API credentials
│   └── token.json           # OAuth tokens
│
├── 📥 Input
│   └── urls_input/
│       └── batch1.txt        # TikTok URLs to process
│
├── 🎨 Assets
│   └── backgrounds/          # Background images
│
├── 📤 Output
│   ├── processed_videos/     # Final processed videos
│   ├── temp/                # Temporary files
│   └── database/            # Status & schedule tracking
```

---

## 🔧 How to Use

### Step 1: Prepare Your URLs
Edit `urls_input/batch1.txt` and add your TikTok URLs:

#### Simple Format (Basic):
```
https://www.tiktok.com/@username/video/1234567890
https://www.tiktok.com/@username/video/0987654321
```

#### Advanced Format (Recommended):
```
URL | Custom Title | Background | Priority | Description
https://www.tiktok.com/@luccaspaniconafloresta/video/7521106895504018693 | Luccas Panico Content | random | normal | Amazing forest adventure content
https://www.tiktok.com/@oberynedits/video/7464703118345866501 | Epic Movie Edits | blur | high | Cinematic movie compilation
```

**Advanced Format Fields:**
- **URL**: TikTok video URL
- **Custom Title**: Your custom YouTube title (AI will enhance it)
- **Background**: `random`, `blur`, `gradient`, `solid`, `specific`
- **Priority**: `high`, `normal`, `low` (processing order)
- **Description**: Custom YouTube description

### Step 2: Configure Settings
Edit `config.yaml` to customize:
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

### Step 3: Run the System

#### For Testing (No YouTube Upload):
```bash
# Just download and process videos
python test_script.py
```

#### For Full Automation:
```bash
# Complete workflow with scheduling
python batch_processor.py
```

#### For Single Video:
```bash
# Process one video manually
python script.py
```

---

## 🎮 Usage Examples

### Example 1: Test Download Only
```bash
# Downloads and processes without uploading
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
