# Gunicorn Configuration for Production
# Save as gunicorn_config.py

import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', 5000)}"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging (send to stdout/stderr for Render compatibility)
accesslog = '-'
errorlog = '-'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Application
preload_app = False
reload = False
reload_extra_files = []

# Process naming
proc_name = 'travel_planner'

# Environment
raw_env = [
    f'FLASK_ENV={os.getenv("FLASK_ENV", "production")}',
    f'PYTHONUNBUFFERED=1'
]
