#!/usr/bin/env python3
"""
AI Scheduler - Asks the AI (Gemini -> OpenAI cascade) to suggest a publish
date/time for each ready-to-upload video, based on its channel and content,
then enforces the hard constraints (spacing_hours, max_daily_uploads) so the
AI's suggestions can never violate them.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class AIScheduler:
    def __init__(self, ai_generator):
        """ai_generator: an AITagsGenerator instance (reused for its Gemini/OpenAI clients)"""
        self.ai_generator = ai_generator

    def _ask_ai_for_slots(self, videos: List[Dict], days_ahead: int, channel_manager=None) -> Optional[List[Dict]]:
        today = datetime.now().strftime('%Y-%m-%d')

        video_lines = []
        for v in videos:
            channel = v.get('target_channel') or v.get('channel', 'default')
            profile = channel_manager.get_channel_profile(channel) if channel_manager else {}
            ai_data = v.get('ai_data', {})
            video_lines.append({
                'video_id': v['video_id'],
                'channel': channel,
                'title': ai_data.get('optimized_title') or v.get('original_title') or v.get('title', ''),
                'content_type': ai_data.get('content_type', 'general'),
                'preferred_days': profile.get('preferred_days') or [],
                'preferred_hours': profile.get('preferred_hours') or []
            })

        prompt = f"""
Today's date is {today}. Suggest a publish date and time (24h format) for each of the
following YouTube Shorts videos, within the next {days_ahead} days. Spread videos from
the same channel across different days/times for steady, non-spammy posting. If a video
lists preferred_days/preferred_hours, prefer those when reasonable.

Videos:
{json.dumps(video_lines, indent=2, ensure_ascii=False)}

Respond ONLY with valid JSON in this exact format:
{{
  "schedule": [
    {{"video_id": "...", "date": "YYYY-MM-DD", "time": "HH:MM"}}
  ]
}}
"""

        for provider in (self.ai_generator.gemini_ai, self.ai_generator.openai_ai):
            if not provider:
                continue
            try:
                call = getattr(provider, 'call_gemini_api', None) or getattr(provider, 'call_openai_api', None)
                if not call:
                    continue
                result = call(prompt)
                if isinstance(result, dict) and 'schedule' in result:
                    return result['schedule']
            except Exception as e:
                print(f"⚠️ AI scheduling call failed: {e}")

        return None

    def create_ai_suggested_schedule(self, videos: List[Dict], config: Dict,
                                      channel_manager=None, days_ahead: int = 7) -> Dict:
        """Returns the same shape as YouTubeScheduler.create_upload_schedule /
        SmartScheduler.create_analytics_based_schedule: a dict with a 'schedule' list."""

        general_cfg = (config or {}).get('general', {})
        scheduling_cfg = (config or {}).get('scheduling', {})
        spacing_hours = scheduling_cfg.get('spacing_hours', 48)
        max_daily = general_cfg.get('max_daily_uploads', 5)

        ai_slots = self._ask_ai_for_slots(videos, days_ahead, channel_manager) or []
        slots_by_video = {}
        for slot in ai_slots:
            try:
                dt = datetime.strptime(f"{slot['date']} {slot['time']}", "%Y-%m-%d %H:%M")
                slots_by_video[slot['video_id']] = dt
            except (KeyError, ValueError):
                continue

        # Fallback for any video the AI didn't return a slot for: next day, default hour
        fallback_dt = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=1)
        for v in videos:
            if v['video_id'] not in slots_by_video:
                slots_by_video[v['video_id']] = fallback_dt
                fallback_dt += timedelta(hours=spacing_hours)

        # Enforce spacing_hours + max_daily_uploads per channel (never trust the AI blindly)
        by_channel: Dict[str, List[Dict]] = {}
        for v in videos:
            channel = v.get('target_channel') or v.get('channel', 'default')
            by_channel.setdefault(channel, []).append(v)

        schedule = []
        for channel, channel_videos in by_channel.items():
            channel_videos.sort(key=lambda v: slots_by_video[v['video_id']])
            last_dt = None
            day_counts: Dict[str, int] = {}

            for v in channel_videos:
                dt = slots_by_video[v['video_id']]

                if last_dt and (dt - last_dt) < timedelta(hours=spacing_hours):
                    dt = last_dt + timedelta(hours=spacing_hours)

                day_key = dt.strftime('%Y-%m-%d')
                while day_counts.get(day_key, 0) >= max_daily:
                    dt += timedelta(days=1)
                    day_key = dt.strftime('%Y-%m-%d')

                day_counts[day_key] = day_counts.get(day_key, 0) + 1
                last_dt = dt

                schedule.append({
                    'video_id': v['video_id'],
                    'title': (v.get('ai_data') or {}).get('optimized_title') or v.get('original_title', 'Untitled'),
                    'channel': channel,
                    'priority': v.get('priority', 'normal'),
                    'scheduled_time': dt.strftime('%Y-%m-%d %H:%M:%S'),
                    'scheduled_time_readable': dt.strftime('%A %d/%m/%Y à %H:%M'),
                    'status': 'scheduled',
                    'ai_suggested': True,
                    'video_data': v
                })

        schedule.sort(key=lambda e: e['scheduled_time'])

        return {
            'created_at': datetime.now().isoformat(),
            'method': 'ai_suggested',
            'total_videos': len(schedule),
            'schedule': schedule
        }
