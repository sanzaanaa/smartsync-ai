from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from downloader import download_media
from database import get_db, User, DownloadHistory, Favorite
from sqlalchemy.orm import Session
from pathlib import Path
import asyncio, threading, json, bcrypt, yt_dlp, uuid
from datetime import datetime, timedelta
from jose import JWTError, jwt

app = FastAPI(title="SmartSync AI API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SECRET_KEY = "your_super_secret_key_change_this_later_12345"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def verify_password(plain_password, hashed_password):
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except:
        return False

def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

class UserCreate(BaseModel):
    username: str
    password: str
    theme_color: str = "purple"

class ThemeUpdate(BaseModel):
    theme_color: str

class DownloadRequest(BaseModel):
    url: str
    format_type: str

class FavoriteCreate(BaseModel):
    title: str
    url: str
    format_type: str

class SummarizeRequest(BaseModel):
    url: str

download_progress = {}

@app.get("/")
async def read_root():
    return FileResponse(Path(__file__).parent / "templates" / "index.html")

@app.post("/register")
async def register(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Hash password ONCE
    hashed_pwd = get_password_hash(user.password)
    
    # Create user
    new_user = User(
        username=user.username, 
        hashed_password=hashed_pwd, 
        theme_color=user.theme_color
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User created successfully!"}

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials - user not found")
    
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials - wrong password")
    
    access_token = create_access_token(data={"sub": user.username})
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "username": user.username, 
        "is_premium": user.is_premium, 
        "theme_color": user.theme_color
    }

@app.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "username": current_user.username, 
        "is_premium": current_user.is_premium, 
        "theme_color": current_user.theme_color
    }

@app.post("/update-theme")
async def update_theme(theme: ThemeUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    valid_themes = ["purple", "red", "green"]
    if theme.theme_color not in valid_themes:
        raise HTTPException(status_code=400, detail="Invalid theme")
    current_user.theme_color = theme.theme_color
    db.commit()
    return {"status": "success", "theme_color": theme.theme_color}

@app.post("/upgrade-to-premium")
async def upgrade_to_premium(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.is_premium = True
    db.commit()
    return {"status": "success"}

@app.post("/favorites")
async def add_favorite(fav: FavoriteCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(Favorite).filter(
        Favorite.user_id == current_user.id, 
        Favorite.url == fav.url
    ).first()
    if existing:
        return {"status": "already_exists"}
    
    db.add(Favorite(
        user_id=current_user.id, 
        title=fav.title, 
        url=fav.url, 
        format_type=fav.format_type
    ))
    db.commit()
    return {"status": "success"}

@app.delete("/favorites/{fav_id}")
async def remove_favorite(fav_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fav = db.query(Favorite).filter(
        Favorite.id == fav_id, 
        Favorite.user_id == current_user.id
    ).first()
    if not fav:
        raise HTTPException(status_code=404, detail="Favorite not found")
    db.delete(fav)
    db.commit()
    return {"status": "success"}

@app.get("/favorites")
async def get_favorites(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    favs = db.query(Favorite).filter(
        Favorite.user_id == current_user.id
    ).order_by(Favorite.added_at.desc()).all()
    return [{
        "id": f.id, 
        "title": f.title, 
        "url": f.url, 
        "format_type": f.format_type, 
        "added_at": f.added_at.strftime("%Y-%m-%d %H:%M")
    } for f in favs]

@app.post("/api/summarize")
async def summarize_video(req: SummarizeRequest, current_user: User = Depends(get_current_user)):
    if not current_user.is_premium:
        raise HTTPException(status_code=403, detail="AI Summary is a Premium feature!")
    
    try:
        ydl_opts = {
            'skip_download': True, 
            'quiet': True, 
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            title = info.get('title', 'Unknown Title')
            desc = info.get('description', '')
            
            if not desc or len(desc) < 50:
                summary = [
                    f"Video: {title}", 
                    "No detailed description provided.", 
                    "Watch the video to learn more!"
                ]
            else:
                lines = [
                    line.strip() for line in desc.split('\n') 
                    if line.strip() and len(line.strip()) > 30 and not line.startswith('http')
                ]
                summary = lines[:3] if lines else [
                    f"About: {title}", 
                    "Check the video for full details."
                ]
            return {"status": "success", "title": title, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")

@app.get("/download-file/{filename}")
async def download_file(filename: str):
    file_path = Path("temp_downloads") / "MP3" / filename
    if not file_path.exists():
        file_path = Path("temp_downloads") / "MP4" / filename
    if file_path.exists():
        return FileResponse(
            file_path, 
            filename=filename, 
            media_type='application/octet-stream'
        )
    raise HTTPException(status_code=404, detail="File not found on server.")

@app.get("/api/stats")
async def get_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total_downloads = db.query(DownloadHistory).filter(
        DownloadHistory.user_id == current_user.id, 
        DownloadHistory.status == 'completed'
    ).count()
    total_favorites = db.query(Favorite).filter(
        Favorite.user_id == current_user.id
    ).count()
    days_member = (datetime.utcnow() - current_user.created_at).days + 1
    return {
        "total_downloads": total_downloads, 
        "total_favorites": total_favorites, 
        "days_member": days_member
    }

@app.get("/progress/{download_id}")
async def get_progress(download_id: str, token: str = None, db: Session = Depends(get_db)):
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            current_user = db.query(User).filter(User.username == payload.get("sub")).first()
        except:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        raise HTTPException(status_code=401, detail="Token required")
    
    async def event_stream():
        while True:
            if download_id in download_progress:
                data = download_progress[download_id]
                yield f"data: {data}\n\n"
                try:
                    if json.loads(data).get('status') in ['success', 'error']:
                        break
                except:
                    pass
            await asyncio.sleep(0.5)
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/download")
async def download_endpoint(
    request: DownloadRequest, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    # Check daily limit for free users
    if not current_user.is_premium:
        today = datetime.utcnow().date()
        count = db.query(DownloadHistory).filter(
            DownloadHistory.user_id == current_user.id, 
            DownloadHistory.downloaded_at >= datetime(today.year, today.month, today.day)
        ).count()
        if count >= 5:
            raise HTTPException(status_code=403, detail="Daily limit reached! Upgrade to Pro.")
    
    # Check if playlist
    is_playlist = 'list=' in request.url or 'playlist' in request.url
    if is_playlist and not current_user.is_premium:
        raise HTTPException(status_code=403, detail="Playlist downloading is a Premium feature!")
    
    download_id = str(uuid.uuid4())
    download_progress[download_id] = json.dumps({"status": "starting..."})
    
    # Create history record
    db_download = DownloadHistory(
        user_id=current_user.id, 
        url=request.url, 
        format_type=request.format_type, 
        status="in_progress", 
        downloaded_at=datetime.utcnow()
    )
    db.add(db_download)
    db.commit()
    db.refresh(db_download)
    record_id = db_download.id
    
    def run_download():
        result = download_media(
            request.url, 
            request.format_type, 
            is_premium=current_user.is_premium, 
            progress_callback=lambda d: download_progress.update({download_id: json.dumps(d)})
        )
        
        # Update database
        db_download = db.query(DownloadHistory).filter(DownloadHistory.id == record_id).first()
        if result['status'] == 'success':
            db_download.title = result.get('title', 'Unknown')
            db_download.filename = result.get('filename', '')
            db_download.status = 'completed'
        else:
            db_download.status = 'failed'
        db.commit()
        download_progress[download_id] = json.dumps(result)
    
    threading.Thread(target=run_download).start()
    return {"download_id": download_id, "status": "started"}

@app.get("/api/history")
async def get_history(
    format_type: str = "all", 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    query = db.query(DownloadHistory).filter(
        DownloadHistory.status == 'completed', 
        DownloadHistory.user_id == current_user.id
    )
    if format_type != "all":
        query = query.filter(DownloadHistory.format_type == format_type)
    
    return [{
        "id": h.id, 
        "title": h.title, 
        "url": h.url, 
        "format_type": h.format_type, 
        "filename": h.filename, 
        "date": h.downloaded_at.strftime("%Y-%m-%d %H:%M")
    } for h in query.order_by(DownloadHistory.downloaded_at.desc()).all()]
