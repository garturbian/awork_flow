import os
import sys
import subprocess
import time
import logging
import queue
import threading
import shutil
import hashlib
import json
import datetime
import argparse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Configuration ---
# Directory to watch for new .wav files (relative to this script's location)
WATCHED_FOLDER_NAME = "Work_room"

# Get the directory where this script is located
# This ensures paths are correct regardless of where the script is executed from
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory for intermediate artifacts
ARTIFACTS_DIR = os.path.join(SCRIPT_DIR, "artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(SCRIPT_DIR, "audio_workflow.log"), encoding="utf-8")]
)
logger = logging.getLogger(__name__)

# Full path to the watched folder
WATCHED_FOLDER_PATH = os.path.join(SCRIPT_DIR, WATCHED_FOLDER_NAME)

# Paths to the batch scripts (relative to SCRIPT_DIR)
PROCESS_AUDIO_SCRIPT = os.path.join(SCRIPT_DIR, "process_audio.bat")
TRANSLATE_SRT_SCRIPT = os.path.join(SCRIPT_DIR, "translate_srt_to_chinese.bat")

# Path to ffmpeg.exe (assuming it's in the same directory as this script)
# If ffmpeg is in your system PATH, you can just use "ffmpeg" instead.
FFMPEG_PATH = os.path.join(SCRIPT_DIR, "ffmpeg.exe")
# FFMPEG_PATH = "ffmpeg" # Use this if relying on PATH

# --- Work Queue and Worker Thread ---
# Create a queue for processing tasks
work_q = queue.Queue()

def worker_loop():
    """Worker thread function that processes tasks from the queue."""
    while True:
        task = work_q.get()
        if task is None:
            break
        try:
            base = task
            logger.info("Worker starting processing for %s", base)
            
            # Load metadata to determine which steps to run
            m = load_meta(base)
            
            if m.get("steps_completed", {}).get("process_audio"):
                # Run steps 2 and 3 only if missing
                if not m.get("steps_completed", {}).get("ass_to_srt"):
                    step2_ass_to_srt(base)
                    # Update metadata
                    meta = load_meta(base)
                    meta.setdefault("steps_completed", {})["ass_to_srt"] = True
                    meta["last_updated"] = datetime.datetime.utcnow().isoformat()
                    save_meta(base, meta)
                    
                if not m.get("steps_completed", {}).get("translate"):
                    step3_translate_srt(base)
                    # Update metadata
                    meta = load_meta(base)
                    meta.setdefault("steps_completed", {})["translate"] = True
                    meta["last_updated"] = datetime.datetime.utcnow().isoformat()
                    save_meta(base, meta)
            else:
                # Run full sequence
                step1_process_audio(base)
                step2_ass_to_srt(base)
                step3_translate_srt(base)
                
                # Update metadata for steps 2 and 3
                meta = load_meta(base)
                meta.setdefault("steps_completed", {})["ass_to_srt"] = True
                meta.setdefault("steps_completed", {})["translate"] = True
                meta["last_updated"] = datetime.datetime.utcnow().isoformat()
                save_meta(base, meta)
                        
        except Exception:
            logger.exception("Worker error processing %s", base)
        finally:
            work_q.task_done()

# Start the worker thread
worker_thread = threading.Thread(target=worker_loop, daemon=True)
worker_thread.start()


# --- Metadata and File Hashing Helpers ---
def meta_path(base):
    """Return the path to the metadata file for a given base filename."""
    return os.path.join(SCRIPT_DIR, f"{base}.meta.json")

def file_hash(path):
    """Calculate SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def load_meta(base):
    """Load metadata from file, returning empty dict if file doesn't exist."""
    p = meta_path(base)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}

def save_meta(base, meta):
    """Save metadata to file atomically."""
    tmp = meta_path(base) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, meta_path(base))


# --- Step Functions ---
def step1_process_audio(base):
    """
    Step 1: Run process_audio.bat to generate ASS file from WAV.
    
    Args:
        base (str): Base filename without extension
        
    Raises:
        subprocess.CalledProcessError: If the subprocess fails
        FileNotFoundError: If expected ASS file is not created
    """
    logger.info("[Step 1] Running process_audio.bat for '%s'...", base)
    # The batch script expects the filename without extension and
    # should be run from the script's directory
    cmd = [PROCESS_AUDIO_SCRIPT, base]
    subprocess.run(
        cmd,
        check=True,              # Raises CalledProcessError on non-zero exit
        capture_output=True,     # Captures stdout and stderr
        text=True,               # Returns strings, not bytes
        cwd=SCRIPT_DIR           # Run in the script's directory
    )
    logger.info("[Step 1] process_audio.bat completed successfully.")
    
    # Check if the .ass file was actually created
    ass_file = os.path.join(SCRIPT_DIR, f"{base}.ass")
    if not os.path.exists(ass_file):
        raise FileNotFoundError(f"Expected .ass file not found: {ass_file}")
    
    # After step1 succeeds, copy .ass to .ass.orig the first time and record hash and meta
    orig = os.path.join(SCRIPT_DIR, f"{base}.ass.orig")
    if not os.path.exists(orig):
        shutil.copy2(ass_file, orig)
        # Wait until the file is stable before computing hash
        if not wait_until_stable(ass_file):
            logger.warning("ASS file %s did not stabilize", ass_file)
            return
        meta = load_meta(base)
        meta["ass_hash"] = file_hash(ass_file)
        meta.setdefault("steps_completed", {})["process_audio"] = True
        meta["last_updated"] = datetime.datetime.utcnow().isoformat()
        save_meta(base, meta)
        
        # Move intermediate files to artifacts directory
        artifacts_dir = os.path.join(ARTIFACTS_DIR, base)
        os.makedirs(artifacts_dir, exist_ok=True)
        
        # Move the .ass file to artifacts directory
        artifacts_ass_file = os.path.join(artifacts_dir, f"{base}.ass")
        shutil.move(ass_file, artifacts_ass_file)
        logger.info("Moved %s to artifacts directory", f"{base}.ass")
        
        # Also move the .ass.orig file to artifacts directory
        orig_artifacts = os.path.join(artifacts_dir, f"{base}.ass.orig")
        if os.path.exists(orig):
            shutil.move(orig, orig_artifacts)
            logger.info("Moved %s to artifacts directory", f"{base}.ass.orig")
        
        # Provide convenience function to open the .ass file
        try:
            os.startfile(artifacts_ass_file)
            logger.info("Opened %s in default editor", artifacts_ass_file)
        except Exception as e:
            logger.debug("Could not open %s: %s", artifacts_ass_file, e)


def step2_ass_to_srt(base):
    """
    Step 2: Convert generated .ass to .srt using ffmpeg.
    
    Args:
        base (str): Base filename without extension
        
    Raises:
        subprocess.CalledProcessError: If the subprocess fails
    """
    logger.info("[Step 2] Converting '%s.ass' to '%s.srt'...", base, base)
    # Use the .ass file from artifacts directory
    artifacts_dir = os.path.join(ARTIFACTS_DIR, base)
    ass_file = os.path.join(artifacts_dir, f"{base}.ass")
    srt_file = os.path.join(SCRIPT_DIR, f"{base}.srt")
    
    # Run ffmpeg to convert .ass to .srt
    # Run it in the script directory
    cmd = [FFMPEG_PATH, "-y", "-i", ass_file, srt_file]
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        cwd=SCRIPT_DIR
    )
    logger.info("[Step 2] Conversion to .srt completed successfully.")


def step3_translate_srt(base):
    """
    Step 3: Run translate_srt_to_chinese.bat to translate SRT file.
    
    Args:
        base (str): Base filename without extension
        
    Raises:
        subprocess.CalledProcessError: If the subprocess fails
    """
    logger.info("[Step 3] Running translate_srt_to_chinese.bat for '%s'...", base)
    # The batch script expects the filename without extension
    cmd = [TRANSLATE_SRT_SCRIPT, base]
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        cwd=SCRIPT_DIR
    )
    logger.info("[Step 3] translate_srt_to_chinese.bat completed successfully.")
    
    # Move all output files to the Work_room folder after completion
    output_files = [
        f"{base}.ass",
        f"{base}.srt",
        f"{base}.mp4",
        f"{base}_zh-tw.srt"
    ]
    
    # Move files from SCRIPT_DIR to Work_room
    for file in output_files:
        src_path = os.path.join(SCRIPT_DIR, file)
        dst_path = os.path.join(WATCHED_FOLDER_PATH, file)
        if os.path.exists(src_path):
            try:
                shutil.move(src_path, dst_path)
                logger.info("         Moved %s to Work_room folder", file)
            except Exception as e:
                logger.warning("         Could not move %s to Work_room folder: %s", file, e)
    
    # Also move the final files from artifacts directory to Work_room if they exist there
    artifacts_dir = os.path.join(ARTIFACTS_DIR, base)
    if os.path.exists(artifacts_dir):
        for file in [f"{base}.ass", f"{base}.ass.orig"]:
            src_path = os.path.join(artifacts_dir, file)
            dst_path = os.path.join(WATCHED_FOLDER_PATH, file)
            if os.path.exists(src_path):
                try:
                    shutil.move(src_path, dst_path)
                    logger.info("         Moved %s from artifacts to Work_room folder", file)
                except Exception as e:
                    logger.warning("         Could not move %s from artifacts to Work_room folder: %s", file, e)
    
    # Provide convenience function to open the final translated SRT file
    final_srt = os.path.join(WATCHED_FOLDER_PATH, f"{base}_zh-tw.srt")
    if os.path.exists(final_srt):
        try:
            os.startfile(final_srt)
            logger.info("Opened final translation %s in default editor", final_srt)
        except Exception as e:
            logger.debug("Could not open %s: %s", final_srt, e)


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


# --- File Event Handlers ---
class AssModifiedHandler(FileSystemEventHandler):
    """Handles file system events for .ass file modifications."""
    
    def on_modified(self, event):
        """Triggered when a file or directory is modified."""
        if event.is_directory:
            return
        if not event.src_path.lower().endswith(".ass"):
            return
            
        base = os.path.splitext(os.path.basename(event.src_path))[0]
        try:
            # wait until stable then compute hash
            if not wait_until_stable(event.src_path):
                logger.warning("Edited .ass %s did not stabilize", event.src_path)
                return
            new_hash = file_hash(event.src_path)
        except Exception:
            return
            
        meta = load_meta(base)
        old_hash = meta.get("ass_hash")
        if old_hash != new_hash:
            logger.info("Detected edited .ass for %s — scheduling downstream steps", base)
            meta["ass_hash"] = new_hash
            meta.setdefault("steps_completed", {}).pop("ass_to_srt", None)
            meta.setdefault("steps_completed", {}).pop("translate", None)
            save_meta(base, meta)
            work_q.put(base)  # worker should be adjusted to run only step2+3 if meta shows process_audio done


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
                
                # Enqueue the task for processing by the worker thread
                logger.info("Enqueuing %s for processing", base_filename)
                work_q.put(base_filename)


# --- Main Script Execution ---
def main():
    """
    Sets up the file watcher and starts the monitoring loop.
    """
    # Parse command line arguments for resume functionality
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", help="base filename to resume, without extension")
    parser.add_argument("--from-step", type=int, default=2, choices=[1, 2, 3])
    args = parser.parse_args()
    
    # Handle resume functionality if requested
    if args.resume:
        base = args.resume
        if args.from_step <= 1:
            # Full run
            work_q.put(base)
        elif args.from_step == 2:
            # Mark process_audio done if needed and enqueue step2+3
            m = load_meta(base)
            m.setdefault("steps_completed", {})["process_audio"] = True
            save_meta(base, m)
            work_q.put(base)
        elif args.from_step == 3:
            # Mark both previous steps done if you want to just run translation
            m = load_meta(base)
            m.setdefault("steps_completed", {})["process_audio"] = True
            m.setdefault("steps_completed", {})["ass_to_srt"] = True
            save_meta(base, m)
            work_q.put(base)
        
        # Process the queue item and exit
        # Wait for the worker to finish
        work_q.join()
        return

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

    # Create the event handlers and observers
    wav_handler = WavHandler()
    ass_handler = AssModifiedHandler()
    observer = Observer()
    
    # Schedule the observer to watch the specified folder for events
    observer.schedule(wav_handler, WATCHED_FOLDER_PATH, recursive=False)
    observer.schedule(ass_handler, SCRIPT_DIR, recursive=False)

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