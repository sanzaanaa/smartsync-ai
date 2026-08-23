FROM python:3.10-slim

# Install ffmpeg and git (required for yt-dlp)
RUN apt-get update && apt-get install -y ffmpeg git

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the port Render will use
EXPOSE 8000

# Command to start the app
   CMD uvicorn main:app --host 0.0.0.0 --port $PORT