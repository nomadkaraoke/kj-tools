import os
import subprocess
import threading
import time
import random
import requests
from flask import Flask, render_template, request, jsonify
import yt_dlp

# --- Configuration ---
KARAOKE_VLC_PORT = 8080
FILLER_VLC_PORT = 8081
KARAOKE_VLC_PASSWORD = "karaoke"
FILLER_VLC_PASSWORD = "filler"
VIDEO_DIR = os.path.expanduser("~/kjdata/videos")
FILLER_MUSIC_PATH = os.path.expanduser("~/kjdata/wii.mp3")
LOG_FILE = os.path.expanduser("~/kj-controller.log")

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Global State ---
# This will hold the subprocess objects for our VLC instances
vlc_processes = {
    "karaoke": None,
    "filler": None
}
current_video_id = None
downloaded_videos = {} # Cache for video titles

# --- Logging ---
def log_message(message):
    """Appends a message to the log file."""
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    print(message)

# --- VLC Management ---
def launch_vlc_instance(name, port, password, media_file=None, loop=False):
    """Launches a VLC instance with the HTTP interface enabled."""
    if vlc_processes[name] and vlc_processes[name].poll() is None:
        log_message(f"VLC instance '{name}' is already running.")
        return

    log_message(f"Launching VLC instance '{name}' on port {port}...")
    command = [
        'cvlc',
        '--extraintf', 'http',
        '--http-host', '0.0.0.0',
        '--http-port', str(port),
        '--http-password', password,
        '--no-video-title-show', # Hide title overlay
    ]
    if media_file:
        command.append(media_file)
    if loop:
        command.extend(['--loop'])

    # For Linux, ensure the display is set correctly
    env = os.environ.copy()
    env['DISPLAY'] = ':0'

    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    vlc_processes[name] = process
    log_message(f"VLC instance '{name}' launched with PID {process.pid}.")
    # Give VLC a moment to start up
    time.sleep(2)

def send_vlc_command(port, password, command):
    """Sends a command to a VLC HTTP interface."""
    # Properly encode the command to handle special characters in file paths
    encoded_command = requests.utils.quote(command)
    url = f"http://localhost:{port}/requests/status.json?command={encoded_command}"
    try:
        # Use a session for potential connection pooling
        s = requests.Session()
        s.auth = ('', password)
        response = s.get(url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        log_message(f"Error sending command to VLC on port {port}: {e}")
        return None

# --- Filler Music Control ---
def control_filler_music(action):
    """Controls the filler music. Actions: 'play', 'pause', 'stop'."""
    if action == 'play':
        # Seek to a random position before playing
        duration_s = 3 * 60 + 30 # Approximate duration of wii.mp3
        random_start = random.randint(0, duration_s - 30) # Avoid starting too close to the end
        send_vlc_command(FILLER_VLC_PORT, FILLER_VLC_PASSWORD, f"seek&val={random_start}")
        time.sleep(0.1)
        send_vlc_command(FILLER_VLC_PORT, FILLER_VLC_PASSWORD, "pl_play")
        log_message("Filler music started.")
    elif action == 'pause':
        send_vlc_command(FILLER_VLC_PORT, FILLER_VLC_PASSWORD, "pl_pause")
        log_message("Filler music paused.")
    elif action == 'stop':
        send_vlc_command(FILLER_VLC_PORT, FILLER_VLC_PASSWORD, "pl_stop")
        log_message("Filler music stopped.")


# --- YouTube Downloader ---
def download_video(youtube_url):
    """Downloads a YouTube video, saves metadata, and returns ID and title."""
    video_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
    # Note: The final extension is determined by yt-dlp, so we handle it later.
    output_template = os.path.join(VIDEO_DIR, f"{video_id}")

    ydl_opts = {
        'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
        'force_overwrites': True,
        'quiet': True,
        'noplaylist': True,
        'writethumbnail': True, # Save thumbnail
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            title = info.get('title', 'Unknown Title')
            # The actual downloaded file path
            downloaded_file = ydl.prepare_filename(info)

            # Save metadata to a .json file
            metadata = {
                "id": video_id,
                "title": title,
                "original_url": youtube_url,
                "download_date": time.time()
            }
            with open(f"{output_template}.json", "w") as f:
                import json
                json.dump(metadata, f)

            log_message(f"Successfully downloaded '{title}' with ID {video_id}")
            # Update our in-memory cache
            downloaded_videos[video_id] = title
            return video_id, title
    except Exception as e:
        log_message(f"Error downloading video: {e}")
        return None, None

# --- Flask Routes ---
@app.route('/')
def index():
    """Serves the main remote control page."""
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def handle_download():
    """Handles the video download request."""
    url = request.json.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400

    log_message(f"Received download request for URL: {url}")
    video_id, title = download_video(url)

    if video_id:
        return jsonify({"success": True, "video_id": video_id, "title": title})
    else:
        return jsonify({"error": "Failed to download video"}), 500

@app.route('/play', methods=['POST'])
def handle_play():
    """Handles the video playback request."""
    global current_video_id
    video_id = request.json.get('video_id')
    if not video_id:
        return jsonify({"error": "Video ID is required"}), 400

    # Find the video file, ignoring the specific extension
    video_path = None
    for f in os.listdir(VIDEO_DIR):
        if f.startswith(video_id) and not f.endswith('.json'):
            video_path = os.path.join(VIDEO_DIR, f)
            break

    if not video_path:
        return jsonify({"error": f"Video with ID {video_id} not found"}), 404

    log_message(f"Received play request for video: {video_path}")
    control_filler_music('pause')
    time.sleep(1) # Give music time to fade

    # Using in_enqueue to add to playlist, then playing the first item
    send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "pl_empty")
    time.sleep(0.1)
    send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, f"in_enqueue&input={video_path}")
    time.sleep(0.1)
    send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "pl_play&id=0")
    time.sleep(0.1)
    send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "fullscreen_on")


    current_video_id = video_id
    return jsonify({"success": True, "message": f"Playing {video_id}"})

@app.route('/control', methods=['POST'])
def handle_control():
    """Handles playback controls like pause, resume, restart."""
    action = request.json.get('action')
    if not action:
        return jsonify({"error": "Action is required"}), 400

    log_message(f"Received control action: {action}")
    if action == 'pause_resume':
        send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "pl_pause")
        # Check if we should resume filler music
        status = send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "")
        if status and status.get('state') == 'paused':
            control_filler_music('play')
        else:
            control_filler_music('pause')
    elif action == 'restart':
        send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "seek&val=0")
    elif action == 'stop':
        send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "pl_stop")
        control_filler_music('play')
        global current_video_id
        current_video_id = None

    return jsonify({"success": True, "message": f"Action '{action}' executed."})

@app.route('/volume', methods=['POST'])
def handle_volume():
    """Handles volume control for karaoke or filler music."""
    target = request.json.get('target')
    level = request.json.get('level') # Should be 0-256 for VLC
    if not all([target, level is not None]):
        return jsonify({"error": "Target and level are required"}), 400

    if target == 'karaoke':
        port, password = KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD
    elif target == 'filler':
        port, password = FILLER_VLC_PORT, FILLER_VLC_PASSWORD
    else:
        return jsonify({"error": "Invalid target"}), 400

    send_vlc_command(port, password, f"volume&val={level}")
    log_message(f"Set volume for '{target}' to {level}")
    return jsonify({"success": True})

@app.route('/videos')
def list_videos():
    """Returns a list of all downloaded videos."""
    return jsonify(downloaded_videos)

@app.route('/status')
def get_status():
    """Gets the status of the karaoke player."""
    status = send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "")
    if status:
        return jsonify({
            "state": status.get('state'),
            "current_video_id": current_video_id,
            "time": status.get('time'),
            "length": status.get('length')
        })
    return jsonify({"error": "Could not get status"}), 500


# --- Main Execution ---
def load_video_cache():
    """Scans the video directory and populates the title cache."""
    log_message("Loading video cache...")
    os.makedirs(VIDEO_DIR, exist_ok=True)
    for filename in os.listdir(VIDEO_DIR):
        if filename.endswith(".json"):
            try:
                with open(os.path.join(VIDEO_DIR, filename), 'r') as f:
                    import json
                    metadata = json.load(f)
                    downloaded_videos[metadata['id']] = metadata['title']
            except Exception as e:
                log_message(f"Could not load metadata from {filename}: {e}")
    log_message(f"Loaded {len(downloaded_videos)} videos into cache.")

def start_app():
    """Initializes and starts the application components."""
    log_message("--- KJ Controller Starting Up ---")
    load_video_cache()

    # Launch VLC instances in separate threads
    threading.Thread(target=launch_vlc_instance, args=("karaoke", KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD), daemon=True).start()
    threading.Thread(target=launch_vlc_instance, args=("filler", FILLER_VLC_PORT, FILLER_VLC_PASSWORD, FILLER_MUSIC_PATH, True), daemon=True).start()

    # Wait for VLC instances to be ready
    time.sleep(3)

    # Start filler music
    control_filler_music('play')

    # Start Flask app
    log_message("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    start_app()
