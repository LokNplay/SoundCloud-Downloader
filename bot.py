import telebot
import subprocess
import os
import shutil
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Retrieve the bot token from environment variables
bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
if not bot_token:
    raise ValueError("The TELEGRAM_BOT_TOKEN environment variable is not set.")

bot = telebot.TeleBot(bot_token)

# Retry decorator for Telegram API calls with exponential backoff
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10),
       retry=retry_if_exception_type((TimeoutError, telebot.apihelper.ApiTelegramException)))
def send_audio_with_retry(chat_id, audio_file, title, performer, duration, reply_to_message_id):
    """Sends an audio file with retry logic for network issues."""
    print(f"Sending audio to chat {chat_id}...")
    return bot.send_audio(
        chat_id,
        audio_file,
        title=title,
        performer=performer,
        duration=duration,
        reply_to_message_id=reply_to_message_id,
        timeout=300
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    print(f"Received message with URL: {url}")
    
    if "soundcloud.com" not in url:
        print("Invalid URL detected, sending reply.")
        bot.reply_to(message, "Please send a valid SoundCloud track URL.")
        return
    
    # Use a temporary directory for downloads, suitable for platforms like Koyeb
    temp_dir = "/tmp"
    folder = None
    
    try:
        print("Processing SoundCloud link...")
        bot.reply_to(message, "Processing your SoundCloud link... This may take a moment.")
        
        # Get info using yt-dlp
        print("Fetching metadata...")
        info_cmd = ['yt-dlp', '--print', "%(uploader)s|||%(title)s|||%(ext)s", url]
        info_output = subprocess.check_output(info_cmd).decode().strip()
        print(f"Metadata received: {info_output}")
        
        artist, title, ext = info_output.split('|||')
        
        # Sanitize artist and title to create a valid folder and filename
        invalid_chars = r'[/\\:*?"<>|()]'
        artist = re.sub(invalid_chars, '_', artist.strip())[:50]
        title = re.sub(invalid_chars, '_', title.strip())[:50]
        print(f"Sanitized artist: {artist}, title: {title}, ext: {ext}")
        
        # Set folder and filename within the temporary directory
        folder = os.path.join(temp_dir, f"{artist} - {title}")
        filename = f"01 {title}.{ext}"
        file_path = os.path.join(folder, filename)
        print(f"Creating folder: {folder}")
        
        os.makedirs(folder, exist_ok=True)
        
        # Download audio with default format
        print("Downloading audio...")
        dl_cmd = [
            'yt-dlp', '-x', '--embed-metadata', '--embed-thumbnail',
            '-o', file_path, url
        ]
        subprocess.check_call(dl_cmd)
        
        # Verify file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Downloaded file not found: {file_path}")
        file_size = os.path.getsize(file_path)
        print(f"Download complete. File size: {file_size} bytes")
        
        # Get duration using ffprobe (more reliable)
        duration = None
        try:
            duration_cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of',
                'default=noprint_wrappers=1:nokey=1', file_path
            ]
            duration_output = subprocess.check_output(duration_cmd).decode().strip()
            duration = int(float(duration_output)) if duration_output else None
            if duration:
                print(f"Duration extracted: {duration} seconds")
        except Exception as e:
            duration = None
            print(f"Duration extraction failed: {str(e)}. Proceeding without it.")
        
        # Tag the file using a temporary tagged file, then replace the original
        print("Tagging audio with metadata...")
        tagged_path = os.path.join(folder, f"01 {title} (tagged).{ext}")
        ffmpeg_cmd = [
            'ffmpeg', '-y', '-i', file_path,
            '-metadata', f"album={title}",
            '-metadata', f"album_artist={artist}",
            '-metadata', "track=01",
            '-codec', 'copy', tagged_path
        ]
        subprocess.check_call(ffmpeg_cmd)
        
        # Replace original with tagged file
        print("Replacing original file with tagged version...")
        os.replace(tagged_path, file_path)
        
        # Send the audio file with retries
        print("Sending audio...")
        try:
            with open(file_path, 'rb') as audio_file:
                send_audio_with_retry(
                    message.chat.id,
                    audio_file,
                    title=title,
                    performer=artist,
                    duration=duration,
                    reply_to_message_id=message.message_id
                )
        except Exception as e:
            print(f"Audio send failed: {str(e)}. Trying as a document...")
            with open(file_path, 'rb') as audio_file:
                bot.send_document(
                    message.chat.id,
                    audio_file,
                    visible_file_name=f"{artist} - {title}.{ext}",
                    caption=f"{artist} - {title}",
                    reply_to_message_id=message.message_id,
                    timeout=300
                )
        
        print("Done! Audio sent successfully.")
        
    except Exception as e:
        print(f"Error processing the link: {str(e)}")
        bot.reply_to(message, f"Error processing the link: {str(e)}. Try again or check the URL.")
        
    finally:
        # Clean up the temporary directory
        if folder and os.path.exists(folder):
            print("Cleaning up...")
            shutil.rmtree(folder)
        else:
            print("No directory to clean up.")

# Start the bot with a long polling timeout to handle long-running operations
print("Starting bot polling...")
bot.polling(timeout=60)
        info_output = subprocess.check_output(info_cmd).decode().strip()
        artist, title, ext = info_output.split('|||')
        
        # Sanitize names
        invalid_chars = r'[/\\:*?"<>|()]'
        artist = re.sub(invalid_chars, '_', artist.strip())[:50]
        title = re.sub(invalid_chars, '_', title.strip())[:50]
        
        # Create download directory
        folder = os.path.join("downloads", f"{artist} - {title}")
        filename = f"01 {title}.{ext}"
        file_path = os.path.join(folder, filename)
        os.makedirs(folder, exist_ok=True)
        
        # Download audio
        dl_cmd = [
            'yt-dlp', '-x', '--embed-metadata', '--embed-thumbnail',
            '-o', file_path, url
        ]
        subprocess.check_call(dl_cmd)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Download failed: {file_path}")
        
        # Process audio
        tagged_path = os.path.join(folder, f"01 {title} (tagged).{ext}")
        ffmpeg_cmd = [
            'ffmpeg', '-y', '-i', file_path,
            '-metadata', f"album={title}",
            '-metadata', f"album_artist={artist}",
            '-metadata', "track=01",
            '-codec', 'copy', tagged_path
        ]
        subprocess.check_call(ffmpeg_cmd)
        os.replace(tagged_path, file_path)
        
        # Get duration
        duration = None
        try:
            duration_cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of',
                'default=noprint_wrappers=1:nokey=1', file_path
            ]
            duration_output = subprocess.check_output(duration_cmd).decode().strip()
            duration = int(float(duration_output)) if duration_output else None
        except Exception as e:
            print(f"Duration extraction failed: {e}")
        
        return file_path, title, artist, duration
    except Exception as e:
        raise Exception(f"Processing error: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if "soundcloud.com" not in url:
        bot.reply_to(message, "Please send a valid SoundCloud track URL.")
        return
    
    try:
        bot.reply_to(message, "Processing your SoundCloud link...")
        file_path, title, artist, duration = process_soundcloud_url(url)
        
        # Send audio
        try:
            with open(file_path, 'rb') as audio_file:
                send_audio_with_retry(
                    message.chat.id,
                    audio_file,
                    title=title,
                    performer=artist,
                    duration=duration,
                    reply_to_message_id=message.message_id
                )
        except Exception as e:
            with open(file_path, 'rb') as audio_file:
                bot.send_document(
                    message.chat.id,
                    audio_file,
                    visible_file_name=f"{artist} - {title}.mp3",
                    reply_to_message_id=message.message_id,
                    timeout=300
                )
        
        # Cleanup
        shutil.rmtree(os.path.dirname(file_path))
        
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}. Please try again.")

# Webhook endpoint
@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad request', 400

# Health check endpoint
@app.route('/healthz')
def health_check():
    return 'OK', 200

if __name__ == '__main__':
    if WEBHOOK_URL:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}")
    app.run(host='0.0.0.0', port=PORT)        info_output = subprocess.check_output(info_cmd).decode().strip()
        artist, title, ext = info_output.split('|||')
        
        # Sanitize names
        invalid_chars = r'[/\\:*?"<>|()]'
        artist = re.sub(invalid_chars, '_', artist.strip())[:50]
        title = re.sub(invalid_chars, '_', title.strip())[:50]
        
        # Create download directory
        folder = os.path.join("downloads", f"{artist} - {title}")
        filename = f"01 {title}.{ext}"
        file_path = os.path.join(folder, filename)
        os.makedirs(folder, exist_ok=True)
        
        # Download audio
        dl_cmd = [
            'yt-dlp', '-x', '--embed-metadata', '--embed-thumbnail',
            '-o', file_path, url
        ]
        subprocess.check_call(dl_cmd)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Download failed: {file_path}")
        
        # Process audio
        tagged_path = os.path.join(folder, f"01 {title} (tagged).{ext}")
        ffmpeg_cmd = [
            'ffmpeg', '-y', '-i', file_path,
            '-metadata', f"album={title}",
            '-metadata', f"album_artist={artist}",
            '-metadata', "track=01",
            '-codec', 'copy', tagged_path
        ]
        subprocess.check_call(ffmpeg_cmd)
        os.replace(tagged_path, file_path)
        
        # Get duration
        duration = None
        try:
            duration_cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of',
                'default=noprint_wrappers=1:nokey=1', file_path
            ]
            duration_output = subprocess.check_output(duration_cmd).decode().strip()
            duration = int(float(duration_output)) if duration_output else None
        except Exception as e:
            print(f"Duration extraction failed: {e}")
        
        return file_path, title, artist, duration
    
    except Exception as e:
        raise Exception(f"Processing error: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if "soundcloud.com" not in url:
        bot.reply_to(message, "Please send a valid SoundCloud track URL.")
        return
    
    try:
        bot.reply_to(message, "Processing your SoundCloud link...")
        
        file_path, title, artist, duration = process_soundcloud_url(url, message)
        
        # Send audio
        try:
            with open(file_path, 'rb') as audio_file:
                send_audio_with_retry(
                    message.chat.id,
                    audio_file,
                    title=title,
                    performer=artist,
                    duration=duration,
                    reply_to_message_id=message.message_id
                )
        except Exception as e:
            with open(file_path, 'rb') as audio_file:
                bot.send_document(
                    message.chat.id,
                    audio_file,
                    visible_file_name=f"{artist} - {title}.mp3",
                    reply_to_message_id=message.message_id,
                    timeout=300
                )
        
        # Cleanup
        shutil.rmtree(os.path.dirname(file_path))
        
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}. Please try again.")

# Webhook endpoint
@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad request', 400

# Health check endpoint
@app.route('/healthz')
def health_check():
    return 'OK', 200

if __name__ == '__main__':
    if WEBHOOK_URL:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}")
    app.run(host='0.0.0.0', port=PORT)        bot.reply_to(message, "Processing your SoundCloud link...")
        
        # Get metadata
        info_cmd = ['yt-dlp', '--print', "%(uploader)s|||%(title)s|||%(ext)s", url]
        info_output = subprocess.check_output(info_cmd).decode().strip()
        artist, title, ext = info_output.split('|||')
        
        # Sanitize names
        invalid_chars = r'[/\\:*?"<>|()]'
        artist = re.sub(invalid_chars, '_', artist.strip())[:50]
        title = re.sub(invalid_chars, '_', title.strip())[:50]
        
        # Prepare paths
        folder = os.path.join("downloads", f"{artist} - {title}")
        filename = f"01 {title}.{ext}"
        file_path = os.path.join(folder, filename)
        
        os.makedirs(folder, exist_ok=True)
        
        # Download audio
        dl_cmd = [
            'yt-dlp', '-x', '--embed-metadata', '--embed-thumbnail',
            '-o', file_path, url
        ]
        subprocess.check_call(dl_cmd)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Download failed: {file_path}")
        
        # Tag audio
        tagged_path = os.path.join(folder, f"01 {title} (tagged).{ext}")
        ffmpeg_cmd = [
            'ffmpeg', '-y', '-i', file_path,
            '-metadata', f"album={title}",
            '-metadata', f"album_artist={artist}",
            '-metadata', "track=01",
            '-codec', 'copy', tagged_path
        ]
        subprocess.check_call(ffmpeg_cmd)
        os.replace(tagged_path, file_path)
        
        # Get duration
        duration = None
        try:
            duration_cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of',
                'default=noprint_wrappers=1:nokey=1', file_path
            ]
            duration_output = subprocess.check_output(duration_cmd).decode().strip()
            duration = int(float(duration_output)) if duration_output else None
        except:
            pass
        
        # Send audio
        try:
            with open(file_path, 'rb') as audio_file:
                send_audio_with_retry(
                    message.chat.id,
                    audio_file,
                    title=title,
                    performer=artist,
                    duration=duration,
                    reply_to_message_id=message.message_id
                )
        except Exception as e:
            with open(file_path, 'rb') as audio_file:
                bot.send_document(
                    message.chat.id,
                    audio_file,
                    visible_file_name=f"{artist} - {title}.{ext}",
                    reply_to_message_id=message.message_id,
                    timeout=300
                )
        
        # Cleanup
        shutil.rmtree(folder)
    
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}. Please try again.")

if __name__ == '__main__':
    if webhook_url:
        bot.remove_webhook()
        bot.set_webhook(url=f"{webhook_url}/{bot_token}")
    bot.polling()
