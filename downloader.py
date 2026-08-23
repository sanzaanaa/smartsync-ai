import yt_dlp
import os
from pathlib import Path


def download_media(url, format_type="mp3", is_premium=False, progress_callback=None):
    # Save to a local folder inside the project (Works on Cloud!)
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
                    progress_callback(
                        {'status': 'downloading', 'percent': percent, 'speed': speed, **extra_data})
                except:
                    pass
            elif d['status'] == 'finished':
                progress_callback(
                    {'status': 'finished', 'message': 'Download complete! Processing...'})

    if format_type == "mp3":
        quality = '320' if is_premium else '128'
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality}],
            'outtmpl': output_path, 'quiet': True, 'no_warnings': True, 'progress_hooks': [progress_hook],
        }
    else:
        if is_premium:
            format_str = 'bestvideo+bestaudio/best'
        else:
            format_str = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'
        ydl_opts = {
            'format': format_str,
            'outtmpl': output_path, 'quiet': True, 'no_warnings': True,
            'merge_output_format': 'mp4', 'progress_hooks': [progress_hook],
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
        return {"status": "error", "message": str(e)}
