import telebot
import subprocess
import os
import shutil
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Get config from environment variables
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
webhook_url = os.getenv("WEBHOOK_URL")
port = int(os.getenv("PORT", 5000))

bot = telebot.TeleBot(bot_token)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10),
       retry=retry_if_exception_type((TimeoutError, telebot.apihelper.ApiTelegramException)))
def send_audio_with_retry(chat_id, audio_file, title, performer, duration, reply_to_message_id):
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
    
    if "soundcloud.com" not in url:
        bot.reply_to(message, "Please send a valid SoundCloud track URL.")
        return
    
    try:
        bot.reply_to(message, "Processing your SoundCloud link...")
        
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