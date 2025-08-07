# KJ Remote Controller

## 1. Overview

The KJ Remote Controller is a web-based application designed to simplify the management of a karaoke night. It provides a remote interface, accessible from any web browser on the local network, to control a dedicated playback machine (e.g., a Linux mini PC) connected to a projector and sound system.

This system was created to solve the problem of managing karaoke playback from a machine that is not easily accessible. It allows the Karaoke Jockey (KJ) to manage the show from a separate computer (like a laptop) by controlling video downloads and playback through a user-friendly web UI, eliminating the need for direct SSH commands for every action.

## 2. Features

*   **Remote Playback Control:** A simple web interface to play, pause, restart, and stop karaoke videos.
*   **YouTube Pre-Downloading:** Download karaoke videos from YouTube in the best possible quality. Each video is assigned a unique ID for easy reference and playback.
*   **Automated Filler Music:** Plays background music from a local file (`~/kjdata/wii.mp3`) during downtime.
*   **Smooth Audio Fading:** Automatically fades the filler music out over 3 seconds when a karaoke video starts, and fades it back in over 3 seconds when a video is paused, stopped, or ends naturally.
*   **Live Status Updates:** The remote interface shows the current player state, the ID of the playing video, and a time progress bar.
*   **Downloaded Song Library:** The interface displays a clickable list of all downloaded songs, making it easy to select the next track.
*   **Independent Volume Controls:** Separate, persistent volume sliders for the karaoke video and the filler music.
*   **Always Fullscreen:** The karaoke video player is configured to always be in fullscreen mode.

## 3. Architecture

The system consists of three main components:

1.  **Backend (Flask Application - `app.py`):**
    *   A Python web server that runs on the playback machine.
    *   It exposes a simple REST API to handle requests from the frontend (e.g., `/download`, `/play`, `/volume`).
    *   It uses `yt-dlp` to download videos from YouTube.
    *   It manages and controls two separate, headless VLC instances using VLC's built-in HTTP interface.

2.  **Playback Engine (VLC Media Player):**
    *   **Karaoke VLC Instance:** Runs on port `8080`. It is responsible for playing the main karaoke videos in fullscreen.
    *   **Filler Music VLC Instance:** Runs on port `8081`. It plays the local filler music file on a loop.
    *   Using two instances allows for independent control and smooth crossfading between the main track and background music.

3.  **Frontend (Web Interface - `templates/index.html`):**
    *   A single HTML page with vanilla JavaScript that acts as the remote control.
    *   It communicates with the Flask backend via `fetch` API calls.
    *   It provides a user-friendly interface for all the system's features.

## 4. Setup and Installation

These instructions are for setting up the controller on a Debian-based Linux system (like Linux Mint or Ubuntu).

### Prerequisites

Ensure you have `vlc`, `python3`, `python3-venv`, and `pip` installed:
```bash
sudo apt-get update
sudo apt-get install vlc python3 python3-venv python3-pip
```

### Installation Steps

1.  **Transfer Files:** Copy the entire `kj-controller` directory to the home directory (`~/`) of your playback machine. You can use `scp` from your main computer:
    ```bash
    scp -r /path/to/local/kj-controller your_user@your_pc_ip:~/
    ```

2.  **Create Data Directory:** The application stores videos and logs in `~/kjdata/`. Create this directory and a subdirectory for videos. Also, place your filler music file here.
    ```bash
    mkdir -p ~/kjdata/videos
    # Copy your filler music to this path:
    # cp /path/to/your/music.mp3 ~/kjdata/wii.mp3
    ```

3.  **Set up Python Environment:** Navigate into the project directory and create a virtual environment.
    ```bash
    cd ~/kj-controller
    python3 -m venv venv
    ```

4.  **Activate Environment & Install Dependencies:**
    ```bash
    source venv/bin/activate
    pip install -r requirements.txt
    ```
    *Note: You must activate the `venv` every time you want to run the application in a new terminal session.*

## 5. Running the Application

1.  **Activate Environment:** If you're in a new terminal, make sure to activate the virtual environment first:
    ```bash
    cd ~/kj-controller
    source venv/bin/activate
    ```

2.  **Run the Server:**
    ```bash
    python3 app.py
    ```
    The server will start, launch the two VLC instances, and begin playing the filler music. You will see log output in the terminal. A more detailed log is also saved to `~/kj-controller.log`.

3.  **Access the Remote:**
    *   Find your playback machine's local IP address (`ip a`).
    *   On another computer on the same network, open a web browser and go to `http://<YOUR_PC_IP>:5000`.

## 6. Configuration

Key parameters can be adjusted at the top of the `app.py` file:

*   `KARAOKE_VLC_PORT`, `FILLER_VLC_PORT`: Ports for the VLC instances.
*   `KARAOKE_VLC_PASSWORD`, `FILLER_VLC_PASSWORD`: Passwords for the VLC HTTP interfaces.
*   `VIDEO_DIR`, `FILLER_MUSIC_PATH`, `LOG_FILE`: Paths for data, music, and logs.
