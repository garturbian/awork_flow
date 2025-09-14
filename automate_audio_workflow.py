import os
import sys
import subprocess
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Configuration ---
# Directory to watch for new .wav files (relative to this script's location)
WATCHED_FOLDER_NAME = "Work_room"

# Get the directory where this script is located
# This ensures paths are correct regardless of where the script is executed from
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Full path to the watched folder
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
                print(f"\n[WAV File Detected] {file_path}")
                
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
    print(f"[START] Processing '{base_filename}.wav'...")

    try:
        # --- Step 1: Run process_audio.bat ---
        print(f"[Step 1/3] Running process_audio.bat for '{base_filename}'...")
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
        print(f"[Step 1/3] process_audio.bat completed successfully.")

        # --- Step 2: Convert .ass to .srt using ffmpeg ---
        print(f"[Step 2/3] Converting '{base_filename}.ass' to '{base_filename}.srt'...")
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
        print(f"[Step 2/3] Conversion to .srt completed successfully.")

        # --- Step 3: Run translate_srt_to_chinese.bat ---
        print(f"[Step 3/3] Running translate_srt_to_chinese.bat for '{base_filename}'...")
        # The batch script expects the filename without extension
        cmd_step3 = [TRANSLATE_SRT_SCRIPT, base_filename]
        result3 = subprocess.run(
            cmd_step3,
            check=True,
            capture_output=True,
            text=True,
            cwd=SCRIPT_DIR
        )
        print(f"[Step 3/3] translate_srt_to_chinese.bat completed successfully.")

        # --- Final Success ---
        final_file = os.path.join(SCRIPT_DIR, f"{base_filename}_zh-tw.srt")
        print(f"[SUCCESS] Finished processing '{base_filename}.wav'.")
        print(f"         Final output file: {final_file}")

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
                    print(f"         Moved {file} to Work_room folder")
                except Exception as e:
                    print(f"         Warning: Could not move {file} to Work_room folder: {e}")

    except subprocess.CalledProcessError as e:
        # This block handles errors from any of the subprocess.run calls
        print(f"[ERROR] A subprocess failed during the processing of '{base_filename}.wav'.")
        print(f"        Failed command: {' '.join(e.cmd)}")
        print(f"        Return code: {e.returncode}")
        if e.stdout:
            print(f"        STDOUT:\n{e.stdout}")
        if e.stderr:
            print(f"        STDERR:\n{e.stderr}")
    except FileNotFoundError as e:
        # Handles specific file not found errors
        print(f"[ERROR] File not found during processing of '{base_filename}.wav': {e}")
    except Exception as e:
        # Handles any other unexpected errors
        print(f"[ERROR] An unexpected error occurred while processing '{base_filename}.wav': {e}")
        print(f"        Details: {type(e).__name__}: {e}")


# --- Main Script Execution ---
def main():
    """
    Sets up the file watcher and starts the monitoring loop.
    """
    print(f"Audio Workflow Automation Script Started.")
    print(f"Watching folder: {WATCHED_FOLDER_PATH}")

    # Verify the watched folder exists
    if not os.path.exists(WATCHED_FOLDER_PATH):
        print(f"[FATAL ERROR] The watched folder '{WATCHED_FOLDER_PATH}' does not exist.")
        print("             Please create the 'Work_room' folder.")
        sys.exit(1)

    # Verify batch scripts exist
    if not os.path.exists(PROCESS_AUDIO_SCRIPT):
        print(f"[FATAL ERROR] Required script not found: {PROCESS_AUDIO_SCRIPT}")
        sys.exit(1)
    if not os.path.exists(TRANSLATE_SRT_SCRIPT):
        print(f"[FATAL ERROR] Required script not found: {TRANSLATE_SRT_SCRIPT}")
        sys.exit(1)

    # Verify ffmpeg exists (if using a specific path)
    if FFMPEG_PATH != "ffmpeg" and not os.path.exists(FFMPEG_PATH):
        print(f"[FATAL ERROR] Required ffmpeg executable not found: {FFMPEG_PATH}")
        print("             Please ensure ffmpeg.exe is in the script directory or adjust FFMPEG_PATH.")
        sys.exit(1)

    # Create the event handler and observer
    event_handler = WavHandler()
    observer = Observer()
    
    # Schedule the observer to watch the specified folder for events
    observer.schedule(event_handler, WATCHED_FOLDER_PATH, recursive=False)

    # Start the observer in a background thread
    observer.start()
    print("Watcher is now active. Press Ctrl+C to stop.")

    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP] Received Ctrl+C. Shutting down watcher...")
        observer.stop()
    
    # Wait for the observer thread to finish
    observer.join()
    print("[STOP] Watcher stopped. Script exited.")


# --- Entry Point ---
if __name__ == "__main__":
    main()