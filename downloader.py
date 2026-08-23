import yt_dlp
import os
from pathlib import Path

def download_media(url, format_type="mp3", is_premium=False, progress_callback=None):
    base_dir = Path("temp_downloads")
    if format_type == "mp3":
        downloads_dir = base_dir / "MP3"
    else:
        downloads_dir = base_dir / "MP4"
    
    downloads_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(downloads_dir / "%(title)s.%(ext)s")

    def progress_hook(d):
        if progress_callback:
            if d['status'] == 'downloading':
                try:
                    percent = d['_percent_str'].strip()
                    speed = d['_speed_str'].strip()
                    extra_data = {}
                    if 'playlist_index' in d and 'playlist_count' in d:
                        extra_data['playlist_index'] = d['playlist_index']
                        extra_data['playlist_count'] = d['playlist_count']
                    progress_callback({'status': 'downloading', 'percent': percent, 'speed': speed, **extra_data})
                except: 
                    pass
            elif d['status'] == 'finished':
                progress_callback({'status': 'finished', 'message': 'Download complete! Processing...'})

    # Enhanced anti-detection options
    common_opts = {
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook],
        'outtmpl': output_path,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android', 'ios'],
                'player_skip': ['webpage', 'configs']
            }
        },
        'retry_sleep': {'extractor': 15},
        'http_headers': {
            'Accept-Language': 'en-us,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
    }

    if format_type == "mp3":
        quality = '320' if is_premium else '128'
        ydl_opts = {
            **common_opts,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality
            }],
        }
    else:
        if is_premium:
            format_str = 'bestvideo+bestaudio/best'
        else:
            format_str = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'
        ydl_opts = {
            **common_opts,
            'format': format_str,
            'merge_output_format': 'mp4',
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if format_type == "mp3": 
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            return {
                "status": "success",
                "filename": os.path.basename(filename),
                "title": info.get('title', 'Unknown')
            }
    except Exception as e:
        error_msg = str(e)
        
        # Better error messages
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            return {
                "status": "error", 
                "message": "YouTube is blocking cloud downloads. Try: 1) Regular videos (not Shorts) 2) Wait 30 mins 3) Use a different video"
            }
        elif "unavailable" in error_msg.lower() or "private" in error_msg.lower():
            return {
                "status": "error", 
                "message": "This video is private, age-restricted, or unavailable. Try a different public video."
            }
        elif "extractor" in error_msg.lower():
            return {
                "status": "error", 
                "message": "YouTube extraction failed. This video might be protected. Try another one."
            }
        else:
            return {"status": "error", "message": f"Download failed: {error_msg[:100]}"}
