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
                    progress_callback({
                        'status': 'downloading', 
                        'percent': percent, 
                        'speed': speed, 
                        **extra_data
                    })
                except: 
                    pass
            elif d['status'] == 'finished':
                progress_callback({
                    'status': 'finished', 
                    'message': 'Download complete! Processing...'
                })

    # Enhanced options for ALL video types
    common_opts = {
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook],
        'outtmpl': output_path,
        # Multiple client strategies
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android', 'ios', 'tv'],
                'player_skip': ['webpage', 'configs']
            }
        },
        'retry_sleep': {'extractor': 10, 'http': 5},
        'http_headers': {
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Connection': 'keep-alive',
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
        error_msg = str(e).lower()
        
        # Specific error messages
        if "sign in" in error_msg or "bot" in error_msg:
            return {
                "status": "error", 
                "message": "YouTube is blocking this download. Try: 1) A different video 2) Wait 30 minutes 3) Use a regular video (not Shorts)"
            }
        elif "unavailable" in error_msg or "private" in error_msg:
            return {
                "status": "error", 
                "message": "This video is private, age-restricted, or unavailable. Try a public video."
            }
        elif "extractor" in error_msg or "youtube" in error_msg:
            return {
                "status": "error", 
                "message": "YouTube extraction failed. This video might be protected. Try another video."
            }
        else:
            return {
                "status": "error", 
                "message": f"Download failed. Try a different video. Error: {str(e)[:80]}"
            }
