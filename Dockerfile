# Use a lightweight Python base image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Install system dependencies: ffmpeg, ffprobe, and git (if needed)
# The commands below are for Debian-based images (like python:slim)
RUN apt-get update && apt-get install -y ffmpeg

# Copy the requirements file and install the Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# The command to run your script

CMD ["python", "bot.py"]
