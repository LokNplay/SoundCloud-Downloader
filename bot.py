import telebot
import subprocess
import os
import shutil
import re
import json
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Retrieve the bot token and proxy URL from environment variables for security and flexibility
bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
if not bot_token:
    raise ValueError("The TELEGRAM_BOT_TOKEN environment variable is not set.")

proxy_url = os.environ.get("PROXY_URL")
if proxy_url:
    # Use a proxy if the PROXY_URL environment variable is set
    telebot.apihelper.proxy = {'https': proxy_url}
    print(f"Using proxy: {proxy_url}")

# Initialize the bot
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

        # Get info using yt-dlp --dump-json
        print("Fetching metadata...")
        info_output = subprocess.check_output(['yt-dlp', '-J', url]).decode()
        info = json.loads(info_output)
        print("Metadata received.")

        invalid_chars = r'[/\\:*?"<>|()]'  # Characters to replace in filenames only

        if 'entries' in info:
            entries = info['entries']
            album = info['title'][:100]  # Preserve original album name, limit to 100 chars
            album_artist = info.get('uploader', 'Various')[:100]  # Preserve original artist
        else:
            entries = [info]
            album = info['title'][:100]
            album_artist = info['uploader'][:100]

        num_tracks = len(entries)
        is_playlist = num_tracks > 1

        # Sanitize folder and filename parts only where needed
        folder_name = re.sub(invalid_chars, '_', f"{album_artist} - {album}")[:100]
        folder = os.path.join(temp_dir, folder_name)
        print(f"Creating folder: {folder}")
        os.makedirs(folder, exist_ok=True)

        if is_playlist:
            bot.reply_to(message, f"Processing SoundCloud playlist '{album}' with {num_tracks} tracks... This may take a while.")
            output_template = os.path.join(folder, '%(playlist_index)02d %(uploader)s - %(title)s.%(ext)s')
        else:
            bot.reply_to(message, f"Processing SoundCloud track '{album}'...")
            output_template = os.path.join(folder, '01 %(title)s.%(ext)s')

        # Download audio with default format, embedding metadata and thumbnail
        print("Downloading audio...")
        dl_cmd = [
            'yt-dlp', '-x', '--embed-metadata', '--embed-thumbnail',
            '-o', output_template, url
        ]
        subprocess.check_call(dl_cmd)

        # Get all downloaded files sorted
        files = sorted([f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))])
        if len(files) != num_tracks:
            # This check is for sanity and to catch unexpected downloads
            print(f"Warning: Expected {num_tracks} files, but found {len(files)}.")
            # A ValueError would be too aggressive here, maybe just a warning is enough.

        for idx, file in enumerate(files):
            file_path = os.path.join(folder, file)
            file_size = os.path.getsize(file_path)
            print(f"File downloaded: {file}, size: {file_size} bytes")

            # Match the entry to the file based on the file index if it's a playlist
            # Otherwise, use the single entry
            entry = entries[idx] if is_playlist else entries[0]
            title = entry['title'][:100]  # Preserve original title
            performer = entry['uploader'][:100]  # Preserve original performer

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
                    print(f"Duration extracted for {file}: {duration} seconds")
            except Exception as e:
                duration = None
                print(f"Duration extraction failed for {file}: {str(e)}. Proceeding without it.")

            # Tag the file using ffmpeg. Use a separate command from download to add specific metadata
            # Corrected logic to explicitly map the audio stream to avoid errors with embedded video streams
            print(f"Tagging audio {file} with metadata...")
            tagged_path = os.path.join(folder, f"{file}.tagged")
            track_str = "01" if num_tracks == 1 else f"{idx + 1}/{num_tracks}"
            
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-i', file_path,
                '-map', '0:a',  # This is the crucial fix: explicitly map only the audio stream
                '-c:a', 'copy', # Copy the audio stream without re-encoding
                '-metadata', f"album={album}",
                '-metadata', f"album_artist={album_artist}",
                '-metadata', f"track={track_str}",
                tagged_path
            ]
            subprocess.check_call(ffmpeg_cmd)

            # Replace original with tagged file
            print(f"Replacing original file {file} with tagged version...")
            os.replace(tagged_path, file_path)

            # Send the audio file with retries
            print(f"Sending audio {file}...")
            try:
                with open(file_path, 'rb') as audio_file:
                    send_audio_with_retry(
                        message.chat.id,
                        audio_file,
                        title=title,
                        performer=performer,
                        duration=duration,
                        reply_to_message_id=message.message_id
                    )
            except Exception as e:
                print(f"Audio send failed for {file}: {str(e)}. Trying as a document...")
                ext = file.rsplit('.', 1)[-1] if '.' in file else 'opus'
                with open(file_path, 'rb') as audio_file:
                    bot.send_document(
                        message.chat.id,
                        audio_file,
                        visible_file_name=f"{performer} - {title}.{ext}",
                        caption=f"{performer} - {title}",
                        reply_to_message_id=message.message_id,
                        timeout=300
                    )

        print("Done! All audio sent successfully.")

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
