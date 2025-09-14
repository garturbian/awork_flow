import os
import sys
import subprocess
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Configuration ---
# Directory to watch for new .wav files (relative to this script's location)
WATCHED_FOLDER_NAME = "Work_room"

# Get the directory where this script is located
# This ensures paths are correct regardless of where the script is executed from
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(SCRIPT_DIR, "audio_workflow.log"), encoding="utf-8")]
)
logger = logging.getLogger(__name__)


# --- Helper Functions ---
def wait_until_stable(path, timeout=60, stable_time=1.0, poll=0.5):
    """
    Wait until a file's size stabilizes, indicating it's finished being written.
    
    Args:
        path (str): Path to the file to monitor
        timeout (int): Maximum time to wait in seconds
        stable_time (float): Time the file size must remain constant to be considered stable
        poll (float): Interval between file size checks in seconds
        
    Returns:
        bool: True if file stabilized, False if timeout was reached
    """
    start = time.time()
    try:
        last_size = os.path.getsize(path)
    except Exception:
        last_size = -1
    stable_since = time.time()
    
    while True:
        time.sleep(poll)
        try:
            size = os.path.getsize(path)
        except Exception:
            size = -1
            
        if size == last_size:
            if time.time() - stable_since >= stable_time:
                return True
        else:
            stable_since = time.time()
            last_size = size
            
        if time.time() - start > timeout:
            return False


# --- Configuration ---
# Directory to watch for new .wav files (relative to this script's location)
WATCHED_FOLDER_PATH = os.path.join(SCRIPT_DIR, WATCHED_FOLDER_NAME)

# Paths to the batch scripts (relative to SCRIPT_DIR)
PROCESS_AUDIO_SCRIPT = os.path.join(SCRIPT_DIR, "process_audio.bat")
TRANSLATE_SRT_SCRIPT = os.path.join(SCRIPT_DIR, "translate_srt_to_chinese.bat")

# Path to ffmpeg.exe (assuming it's in the same directory as this script)
# If ffmpeg is in your system PATH, you can just use "ffmpeg" instead.
FFMPEG_PATH = os.path.join(SCRIPT_DIR, "ffmpeg.exe")
# FFMPEG_PATH = "ffmpeg" # Use this if relying on PATH

# --- Custom Event Handler ---
class WavHandler(FileSystemEventHandler):
    """
    Handles file system events. Specifically looks for new .wav files.
    """
    def on_created(self, event):
        """
        Triggered when a file or directory is created.
        """
        # We only care about files, not directories
        if not event.is_directory:
            # Get the full path of the created file
            file_path = event.src_path
            
            # Check if the file has a .wav extension (case-insensitive)
            if file_path.lower().endswith('.wav'):
                logger.info("[WAV File Detected] %s", file_path)
                
                # Wait until the file is completely written (size stabilizes)
                if not wait_until_stable(file_path):
                    logger.warning("File %s did not stabilize in time; skipping for now", file_path)
                    return
                
                # Extract the base filename without the .wav extension
                # e.g., "C:\path\work_room\myfile.wav" -> "myfile"
                base_filename = os.path.splitext(os.path.basename(file_path))[0]
                
                # Start the processing workflow for this file
                # This runs in the observer's thread. For heavy tasks,
                # consider using a queue and a worker thread.
                process_wav_file(base_filename)


# --- Core Processing Logic ---
def process_wav_file(base_filename):
    """
    Executes the full workflow for a given .wav file base name.
    Assumes the .wav file exists in WATCHED_FOLDER_PATH.
    Steps:
    1. Run process_audio.bat
    2. Convert generated .ass to .srt using ffmpeg
    3. Run translate_srt_to_chinese.bat
    """
    logger.info("[START] Processing '%s.wav'...", base_filename)

    try:
        # --- Step 1: Run process_audio.bat ---
        logger.info("[Step 1/3] Running process_audio.bat for '%s'...", base_filename)
        # The batch script expects the filename without extension and
        # should be run from the script's directory
        cmd_step1 = [PROCESS_AUDIO_SCRIPT, base_filename]
        result1 = subprocess.run(
            cmd_step1,
            check=True,              # Raises CalledProcessError on non-zero exit
            capture_output=True,     # Captures stdout and stderr
            text=True,               # Returns strings, not bytes
            cwd=SCRIPT_DIR           # Run in the script's directory
        )
        logger.info("[Step 1/3] process_audio.bat completed successfully.")

        # --- Step 2: Convert .ass to .srt using ffmpeg ---
        logger.info("[Step 2/3] Converting '%s.ass' to '%s.srt'...", base_filename, base_filename)
        # The batch script creates files in SCRIPT_DIR, not WATCHED_FOLDER_PATH
        ass_file = os.path.join(SCRIPT_DIR, f"{base_filename}.ass")
        srt_file = os.path.join(SCRIPT_DIR, f"{base_filename}.srt")

        # Check if the .ass file was actually created by process_audio.bat
        if not os.path.exists(ass_file):
             raise FileNotFoundError(f"Expected .ass file not found: {ass_file}")

        # Run ffmpeg to convert .ass to .srt
        # Run it in the script directory
        cmd_step2 = [FFMPEG_PATH, "-y", "-i", ass_file, srt_file]
        result2 = subprocess.run(
            cmd_step2,
            check=True,
            capture_output=True,
            text=True,
            cwd=SCRIPT_DIR
        )
        logger.info("[Step 2/3] Conversion to .srt completed successfully.")

        # --- Step 3: Run translate_srt_to_chinese.bat ---
        logger.info("[Step 3/3] Running translate_srt_to_chinese.bat for '%s'...", base_filename)
        # The batch script expects the filename without extension
        cmd_step3 = [TRANSLATE_SRT_SCRIPT, base_filename]
        result3 = subprocess.run(
            cmd_step3,
            check=True,
            capture_output=True,
            text=True,
            cwd=SCRIPT_DIR
        )
        logger.info("[Step 3/3] translate_srt_to_chinese.bat completed successfully.")

        # --- Final Success ---
        final_file = os.path.join(SCRIPT_DIR, f"{base_filename}_zh-tw.srt")
        logger.info("[SUCCESS] Finished processing '%s.wav'.", base_filename)
        logger.info("         Final output file: %s", final_file)

        # Move all output files to the Work_room folder
        output_files = [
            f"{base_filename}.ass",
            f"{base_filename}.srt",
            f"{base_filename}.mp4",
            f"{base_filename}_zh-tw.srt"
        ]
        
        for file in output_files:
            src_path = os.path.join(SCRIPT_DIR, file)
            dst_path = os.path.join(WATCHED_FOLDER_PATH, file)
            if os.path.exists(src_path):
                try:
                    os.rename(src_path, dst_path)
                    logger.info("         Moved %s to Work_room folder", file)
                except Exception as e:
                    logger.warning("         Could not move %s to Work_room folder: %s", file, e)

    except subprocess.CalledProcessError as e:
        # This block handles errors from any of the subprocess.run calls
        logger.error("[ERROR] A subprocess failed during the processing of '%s.wav'.", base_filename)
        logger.error("        Failed command: %s", ' '.join(e.cmd))
        logger.error("        Return code: %s", e.returncode)
        if e.stdout:
            logger.error("        STDOUT:\n%s", e.stdout)
        if e.stderr:
            logger.error("        STDERR:\n%s", e.stderr)
    except FileNotFoundError as e:
        # Handles specific file not found errors
        logger.error("[ERROR] File not found during processing of '%s.wav': %s", base_filename, e)
    except Exception as e:
        # Handles any other unexpected errors
        logger.exception("An unexpected error occurred while processing %s", base_filename)


# --- Main Script Execution ---
def main():
    """
    Sets up the file watcher and starts the monitoring loop.
    """
    logger.info("Audio Workflow Automation Script Started.")
    logger.info("Watching folder: %s", WATCHED_FOLDER_PATH)

    # Verify the watched folder exists
    if not os.path.exists(WATCHED_FOLDER_PATH):
        logger.error("[FATAL ERROR] The watched folder '%s' does not exist.", WATCHED_FOLDER_PATH)
        logger.error("             Please create the 'Work_room' folder.")
        sys.exit(1)

    # Verify batch scripts exist
    if not os.path.exists(PROCESS_AUDIO_SCRIPT):
        logger.error("[FATAL ERROR] Required script not found: %s", PROCESS_AUDIO_SCRIPT)
        sys.exit(1)
    if not os.path.exists(TRANSLATE_SRT_SCRIPT):
        logger.error("[FATAL ERROR] Required script not found: %s", TRANSLATE_SRT_SCRIPT)
        sys.exit(1)

    # Verify ffmpeg exists (if using a specific path)
    if FFMPEG_PATH != "ffmpeg" and not os.path.exists(FFMPEG_PATH):
        logger.error("[FATAL ERROR] Required ffmpeg executable not found: %s", FFMPEG_PATH)
        logger.error("             Please ensure ffmpeg.exe is in the script directory or adjust FFMPEG_PATH.")
        sys.exit(1)

    # Create the event handler and observer
    event_handler = WavHandler()
    observer = Observer()
    
    # Schedule the observer to watch the specified folder for events
    observer.schedule(event_handler, WATCHED_FOLDER_PATH, recursive=False)

    # Start the observer in a background thread
    observer.start()
    logger.info("Watcher is now active. Press Ctrl+C to stop.")

    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[STOP] Received Ctrl+C. Shutting down watcher...")
        observer.stop()
    
    # Wait for the observer thread to finish
    observer.join()
    logger.info("[STOP] Watcher stopped. Script exited.")


# --- Entry Point ---
if __name__ == "__main__":
    main()