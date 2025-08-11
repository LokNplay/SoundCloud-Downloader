#!/bin/bash

# Start the health check server in the background
python health_check_server.py &

# Start your bot in the foreground (this will be the main process)
python bot.py
