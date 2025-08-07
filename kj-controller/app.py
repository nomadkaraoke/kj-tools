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
filler_music_target_volume = 100 # Default volume for filler music (0-256)
karaoke_player_is_active = False # Tracks if a karaoke song is supposed to be playing

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
    # Make the karaoke player always start in fullscreen
    if name == 'karaoke':
        command.append('--fullscreen')
        
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

def send_vlc_command(port, password, command, is_path=False):
    """Sends a command to a VLC HTTP interface."""
    # The query part of the URL needs to be handled carefully.
    # The 'command' part is the key, and the rest is the value.
    # For file paths, we need to be extra careful with encoding.
    if '&' in command and not is_path:
        # Simple command like 'seek&val=0'
        url = f"http://localhost:{port}/requests/status.json?command={command}"
    else:
        # Command with input, like 'in_play&input=...'
        parts = command.split('&input=', 1)
        cmd_part = parts[0]
        input_part = parts[1] if len(parts) > 1 else ''
        
        # URL encode only the input part (the file path)
        encoded_input = requests.utils.quote(input_part)
        url = f"http://localhost:{port}/requests/status.json?command={cmd_part}&input={encoded_input}"

    log_message(f"DEBUG: Sending VLC command to {url}")
    try:
        s = requests.Session()
        s.auth = ('', password)
        response = s.get(url, timeout=5)
        log_message(f"DEBUG: VLC response status: {response.status_code}")
        response_json = response.json()
        log_message(f"DEBUG: VLC response body: {response_json}")
        response.raise_for_status()
        return response_json
    except requests.exceptions.RequestException as e:
        log_message(f"Error sending command to VLC on port {port}: {e}")
        return None
    except Exception as e:
        log_message(f"An unexpected error occurred when calling VLC: {e}")
        return None

# --- Fading and Music Control ---
def fade_music(port, password, start_vol, end_vol, duration_s=3):
    """Gradually fades volume over a set duration."""
    steps = 20
    delay = duration_s / steps
    for i in range(steps + 1):
        volume = int(start_vol + (end_vol - start_vol) * (i / steps))
        send_vlc_command(port, password, f"volume&val={volume}")
        time.sleep(delay)

def fade_in_filler():
    """Fades in the filler music."""
    log_message("Fading in filler music...")
    # Ensure it's playing, but at 0 volume first
    send_vlc_command(FILLER_VLC_PORT, FILLER_VLC_PASSWORD, "volume&val=0")
    send_vlc_command(FILLER_VLC_PORT, FILLER_VLC_PASSWORD, "pl_play")
    threading.Thread(target=fade_music, args=(FILLER_VLC_PORT, FILLER_VLC_PASSWORD, 0, filler_music_target_volume)).start()

def fade_out_filler():
    """Fades out the filler music and then pauses it."""
    log_message("Fading out filler music...")
    def fade_and_pause():
        fade_music(FILLER_VLC_PORT, FILLER_VLC_PASSWORD, filler_music_target_volume, 0)
        send_vlc_command(FILLER_VLC_PORT, FILLER_VLC_PASSWORD, "pl_pause")
        log_message("Filler music faded out and paused.")
    threading.Thread(target=fade_and_pause).start()


# --- YouTube Downloader ---
def download_video(youtube_url):
    """Downloads a YouTube video, saves metadata, and returns ID and title."""
    video_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
    # Note: The final extension is determined by yt-dlp, so we handle it later.
    output_template = os.path.join(VIDEO_DIR, f"{video_id}")

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
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
        if f.startswith(video_id) and not f.endswith(('.json', '.webp', '.jpg')): # Exclude metadata/thumbnails
            video_path = os.path.join(VIDEO_DIR, f)
            break

    if not video_path:
        log_message(f"ERROR: Video file for ID '{video_id}' not found in {VIDEO_DIR}")
        return jsonify({"error": f"Video file for ID {video_id} not found"}), 404

    log_message(f"Attempting to play video: {video_path}")
    
    fade_out_filler()
    time.sleep(3.5) # Wait for fade to complete

    log_message("Sending commands to Karaoke VLC...")
    # 1. Clear the playlist
    send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "pl_empty")
    time.sleep(0.2)
    
    # 2. Add the new video and play it immediately. This is more reliable.
    play_command = f"in_play&input={video_path}"
    play_response = send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, play_command, is_path=True)
    time.sleep(0.2)

    # 3. Verify playback state
    time.sleep(1) # Give VLC a moment to update its state
    status = send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "")
    if status and status.get('state') == 'playing':
        log_message(f"SUCCESS: VLC reports playback started for {video_id}.")
        global karaoke_player_is_active
        karaoke_player_is_active = True
        current_video_id = video_id
        return jsonify({"success": True, "message": f"Playing {video_id}"})
    else:
        log_message(f"ERROR: VLC did not confirm playback for {video_id}. Last status: {status}")
        # Attempt to restart filler music as a fallback
        fade_in_filler()
        return jsonify({"error": "VLC did not confirm playback. Check logs.", "vlc_status": status}), 500

@app.route('/control', methods=['POST'])
def handle_control():
    """Handles playback controls like pause, resume, restart."""
    action = request.json.get('action')
    if not action:
        return jsonify({"error": "Action is required"}), 400

    log_message(f"Received control action: {action}")
    global karaoke_player_is_active
    if action == 'pause_resume':
        send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "pl_pause")
        # Check if we should resume filler music
        time.sleep(0.5) # Give vlc time to process
        status = send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "")
        if status and status.get('state') == 'paused':
            karaoke_player_is_active = False
            fade_in_filler()
        else:
            karaoke_player_is_active = True
            fade_out_filler()
    elif action == 'restart':
        send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "seek&val=0")
    elif action == 'stop':
        send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "pl_stop")
        karaoke_player_is_active = False
        global current_video_id
        current_video_id = None
        fade_in_filler()

    return jsonify({"success": True, "message": f"Action '{action}' executed."})

@app.route('/volume', methods=['POST'])
def handle_volume():
    """Handles volume control for karaoke or filler music."""
    target = request.json.get('target')
    level = int(request.json.get('level')) # Should be 0-256 for VLC
    if not all([target, level is not None]):
        return jsonify({"error": "Target and level are required"}), 400

    if target == 'karaoke':
        port, password = KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD
    elif target == 'filler':
        port, password = FILLER_VLC_PORT, FILLER_VLC_PASSWORD
        global filler_music_target_volume
        filler_music_target_volume = level
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

def monitor_karaoke_player():
    """A background thread to check if a song has ended and trigger filler music."""
    global karaoke_player_is_active, current_video_id
    while True:
        time.sleep(2)
        if not karaoke_player_is_active:
            continue

        status = send_vlc_command(KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD, "")
        # 'state' becomes 'stopped' when a video finishes
        if status and status.get('state') == 'stopped':
            log_message("Karaoke video finished playing.")
            karaoke_player_is_active = False
            current_video_id = None
            fade_in_filler()

def start_app():
    """Initializes and starts the application components."""
    log_message("--- KJ Controller Starting Up ---")
    load_video_cache()

    # Launch VLC instances
    launch_vlc_instance("karaoke", KARAOKE_VLC_PORT, KARAOKE_VLC_PASSWORD)
    launch_vlc_instance("filler", FILLER_VLC_PORT, FILLER_VLC_PASSWORD, FILLER_MUSIC_PATH, True)

    # Wait for VLC instances to be ready
    time.sleep(3)

    # Start filler music
    fade_in_filler()

    # Start the karaoke player monitor in a background thread
    monitor_thread = threading.Thread(target=monitor_karaoke_player, daemon=True)
    monitor_thread.start()

    # Start Flask app
    log_message("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    start_app()
