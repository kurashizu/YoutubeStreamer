# YOUTUBE_VIDEO_URL="https://youtu.be/rvoMcy62AX0?si=M7lJqiGW8NYu_tS3"

import threading
import subprocess
import json
import re
import tempfile
import time
import os
import psutil

VERSION_STRING = "v1.4"

class Streamer:
    def __init__(self, RTMP_BASE_URL = "",
                 RTMP_STREAM_KEY = "",
                 perfmon = None):
        
        self.version = VERSION_STRING

        self.perfmon = perfmon

        self.RTMP_URL = f"{RTMP_BASE_URL}{RTMP_STREAM_KEY}"
        self.RTMP_STREAM_KEY = RTMP_STREAM_KEY
        self.TIMEOUT_YTDLP = 10

        # playlist represented by Meta data
        # one element is a dict ,for example: 
        # {"url": "https://youtu.be/123", "title"： "Example", 
        # "stream_url", "https://123", ...}
        self.queue = []

        self.streamer = None
        self.streamer_log = {
            "stdout": [],
            "stderr": [],
        }
        self.idle_streamer = None

        self.current_metadata = None
        self.watermark_header = tempfile.NamedTemporaryFile(mode='w+t', delete=True, dir=tempfile.gettempdir())
        self.watermark_playlist_prewrite = tempfile.NamedTemporaryFile(mode='w+t', delete=True, dir=tempfile.gettempdir())
        self.watermark_playlist = tempfile.NamedTemporaryFile(mode='w+t', delete=True, dir=tempfile.gettempdir())

        self.IDLE_STREAM_FPS = 60
        self.IDLE_STREAM_GOP = 300

        self.YTDLP_COOKIE_YOUTUBE = "./www.youtube.com_cookies.txt"
        self.YTDLP_COOKIE_BILIBILI = "./www.bilibili.com_cookies.txt"

        self.YTDLP_FILTER_STRING = "bestvideo[height<=1080][ext=mp4][vcodec^=avc]/b,bestaudio[ext=m4a]/b"

        self.USER_AGENT_STRING = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0"

        threading.Thread(target=self._worker_playlist, daemon=True).start()
        pass

    def add_to_queue(self, url: str = "",
                    stream_bitrate: str = "1200k",
                    stream_audioOnly: bool = False,
                    stream_FPS: int = 60,
                    stream_GOP: int = 300,
                    index: int = None,) -> dict:
        """
        Add an item to queue at the index position
        If index is None, add to the end of the queue
        """

        def _get_metadata(url: str = "", cookie_file: str = None) -> dict:
            """
            Get the metadata of a video by using yt-dlp
            """
            command = [
                "yt-dlp",
                "--print", "%(title)s",
                "--print", "duration",
                "--no-warnings",
                *(["--cookies", cookie_file] if cookie_file else []),
                "-f", f"{self.YTDLP_FILTER_STRING}",
                "--get-url",
                url
            ]
            try:
                process = subprocess.run(command, 
                                        capture_output=True, 
                                        text=True, check=True, 
                                        timeout=self.TIMEOUT_YTDLP)
            except subprocess.TimeoutExpired:
                raise TimeoutError(f"yt-dlp timed out after {self.TIMEOUT_YTDLP} seconds for URL: {url}")
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"yt-dlp failed with error: {e.stderr}")
            except Exception as e:
                raise RuntimeError(f"An unexpected error occurred: {e}")
                
            output_lines = process.stdout.strip().split('\n')

            for i in output_lines:
                print(i)
            
            if len(output_lines) != 6:
                raise ValueError("Unexpected output format")

            if not output_lines[2].startswith("https://"):
                raise ValueError("Invalid video URL")
            if not output_lines[5].startswith("https://"):
                raise ValueError("Invalid audio URL")
            
            start_time_match = re.search(r'[?&]t=(\d+)', url)
            start_time = start_time_match.group(1) if start_time_match else "0"

            return {
                "url": url,
                "title": output_lines[0],
                "total_time": output_lines[1],
                "start_time": start_time,
                "stream_url_video": output_lines[2],
                "stream_url_audio": output_lines[5],
            }
        
        # extract url
        try:
            valid_url = re.findall(r'(https?://\S+)', url)[0]
        except IndexError as e:
            return {
                "success": False, # error
                "message": str(e)
            }
        print("Detected URLs:", valid_url)

        # determine which platform (which cookie_file to use)
        cookie_file = None
        if "youtu.be" in valid_url or "youtube.com" in valid_url:
            cookie_file = self.YTDLP_COOKIE_YOUTUBE
        elif "bilibili.com" in valid_url:
            cookie_file = self.YTDLP_COOKIE_BILIBILI
        
        try:
            metadata = _get_metadata(valid_url, cookie_file)
        except (TimeoutError, RuntimeError, ValueError) as e:
            print(str(e))
            return {
                "success": False, # error
                "message": str(e)
            }
        
        metadata["stream_bitrate"] = stream_bitrate
        metadata["stream_audioOnly"] = stream_audioOnly
        metadata["stream_FPS"] = stream_FPS
        metadata["stream_GOP"] = stream_GOP
        
        if index is None or index >= len(self.queue):
            self.queue.append(metadata)
        else:
            self.queue.insert(index, metadata)
        
        return {
            "success": True, # success
            "message": "Added to queue",
            "queue": self.queue
        }

    def remove_from_queue(self, index: int = None) -> dict:
        """
        Remove a URL from queue at the index position
        By default, remove the last URL in the queue
        """
        if len(self.queue) == 0:
            return {
                "success": False, # error
                "message": "Queue is empty",
                "queue": self.queue,
            }

        if index is None or index >= len(self.queue):
            self.queue.pop()
        else:
            self.queue.pop(index)

        return {
            "success": True, # success
            "message": "Removed from queue",
            "queue": self.queue
        }

    def get_queue(self) -> list:
        """
        Get the queue
        Simple return the queue list
        """
        return self.queue

    def _worker_playlist(self):
        """
        The thread that does queue maintainance
        Automatically put video from queue to streamer if exists
        """
        while True:
            is_streamer_running = self.get_streamer_status()["running"]

            if is_streamer_running:
                # update watermark_playlist
                with open(self.watermark_playlist_prewrite.name, 'w') as f:
                    if self.queue:
                        f.write("Queue:\n")
                        for i, item in enumerate(self.queue[:3]):
                            escaped_title = item['title'].replace('\\', '\\\\').replace('%', '\\%')
                            f.write(f"{i+1}. [{item['total_time']}s] [{'AudioOnly' if item['stream_audioOnly'] else item['stream_bitrate']}] {escaped_title}\n")
                        if len(self.queue) > 3:
                            f.write(f"...and {len(self.queue) - 3} more\n")
                    else:
                        f.write("No video in queue.\n")
                    f.write("\n" + self.perfmon.get_performance_string().replace("%", "\\%") + "\n")
                os.replace(self.watermark_playlist_prewrite.name, self.watermark_playlist.name)
                time.sleep(1)

            else:
                if self.queue:
                    self._stop_idle_streamer()
                    # Start streaming the next video
                    metadata = self.queue.pop(0)
                    print(f"Starting next video, title: {metadata['title']}")
                    self.start_streamer(metadata)
                else:
                    # No video in queue, start idle streamer
                    is_idle_streamer_running = self._is_idle_streamer_running()
                    if not is_idle_streamer_running:
                        self._start_idle_streamer()
                        time.sleep(2)
                        while not self._is_idle_streamer_running():
                            time.sleep(1)
                    else:
                        # update dynamic watermark for idle streamer
                        with open(self.watermark_playlist_prewrite.name, 'w') as f:
                            f.write(self.perfmon.get_performance_string().replace("%", "\\%") + "\n")
                        os.replace(self.watermark_playlist_prewrite.name, self.watermark_playlist.name)
                        time.sleep(1)

    def _thread_streamer_log_stdout(self, stdout, stderr):
        for line in iter(stdout.readline, b''):
            self.streamer_log["stdout"].append(line.decode('utf-8').strip())
        pass

    def _thread_streamer_log_stderr(self, stdout, stderr):
        for line in iter(stderr.readline, b''):
            self.streamer_log["stderr"].append(line.decode('utf-8').strip())
        pass

    def get_endpoint_string(self):
        endpoint_map = {
            "yt": "primary",
        }
        return endpoint_map.get(self.RTMP_STREAM_KEY, self.RTMP_STREAM_KEY)

    def start_streamer(self, metadata):
        """
        Start a streamer process (ffmpeg)
        """

        with open(self.watermark_header.name, 'w') as f:
            f.write(f"Youtube Streamer {VERSION_STRING}@{self.get_endpoint_string()} (by kurashizu)\n")
            escaped_title = metadata['title'].replace('\\', '\\\\').replace('%', '\\%')
            f.write(f"Title: {escaped_title}\n")
            f.write(f"Re-encoded: [Bitrate: {metadata['stream_bitrate']} (bps), FPS: {metadata['stream_FPS']}, GOP: {metadata['stream_GOP']}]\n"
                    if not metadata["stream_audioOnly"] else "Audio Only\n")
            f.write(r"Progress: %{eif:t+" + metadata["start_time"] + r":d} / " + f"{metadata['total_time']} (s)\n")

        vf = f"drawtext=fontfile=./font.ttc:textfile='{self.watermark_header.name}'"
        vf += ":x=20:y=20:borderw=2:bordercolor=black:fontcolor=white:fontsize=24:shadowcolor=black@0.5:shadowx=2:shadowy=2,"
        vf += f"drawtext=fontfile=./font.ttc:textfile='{self.watermark_playlist.name}':reload=1"
        vf += ":x=20:y=h-th-20:borderw=2:bordercolor=black:fontcolor=white:fontsize=24:shadowcolor=black@0.5:shadowx=2:shadowy=2,"

        if metadata["stream_audioOnly"]:
            # if audio only, show "Audio Only" watermark in the center
            vf += f"drawtext=fontfile=./font.ttc:text='Audio Only':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=48:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=5,"

        vf += "format=nv12,hwupload"

        command = ["ffmpeg",
            "-loglevel", "warning",
            "-init_hw_device", "vaapi=va:/dev/dri/renderD128",
            "-hwaccel", "vaapi",
            "-re",

            *(["-fflags", "+genpts",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-ss", metadata["start_time"],
            "-i", metadata["stream_url_video"]] if not metadata["stream_audioOnly"] else [
            # black screen input
            "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:r={metadata['stream_FPS']}",
            ]),
            
            "-fflags", "+genpts",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-ss", metadata["start_time"],
            "-i", metadata["stream_url_audio"],
            "-vf", vf,
            "-c:v", "h264_vaapi", "-b:v", metadata["stream_bitrate"], "-maxrate", metadata["stream_bitrate"],
            "-bufsize", str(int(re.sub(r'k$', r'', metadata["stream_bitrate"])) * 2) + "k",
            "-r", f"{metadata['stream_FPS']}", # Example FPS
            "-g", f"{metadata['stream_GOP']}", "-keyint_min", f"{metadata['stream_GOP']}", # Example GOP
            "-af", "aresample=async=1", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-f", "flv",
            self.RTMP_URL
        ]
        self.streamer = subprocess.Popen(command, 
                                        stdout=subprocess.PIPE, 
                                        stderr=subprocess.PIPE)
        print(f"Streamer started with PID: {self.streamer.pid}")

        self.streamer_log = {
            "stdout": self.streamer_log["stdout"][-100:],
            "stderr": self.streamer_log["stderr"][-100:],
        }
        self.current_metadata = metadata
        threading.Thread(target=self._thread_streamer_log_stdout, args=(self.streamer.stdout, self.streamer.stderr), daemon=True).start()
        threading.Thread(target=self._thread_streamer_log_stderr, args=(self.streamer.stdout, self.streamer.stderr), daemon=True).start()
        pass

    def stop_streamer(self):
        """
        Stop the streamer process
        """
        if self.streamer:
            print(f"Stopping streamer@{self.get_endpoint_string()} with PID: {self.streamer.pid}")
            self.streamer.terminate()
            try:
                self.streamer.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"Streamer@{self.get_endpoint_string()} with PID {self.streamer.pid} did not terminate gracefully, killing.")
                self.streamer.kill()
                self.streamer.wait()
            print(f"Streamer@{self.get_endpoint_string()} stopped.")
        else:
            print(f"No streamer@{self.get_endpoint_string()} to stop.")
        pass

    def get_streamer_status(self) -> dict:
        """
        Get the status of the streamer process
        """
        if self.streamer:
            poll = self.streamer.poll()
            if poll is None:
                # Process is still running
                status = {
                    "running": True, # running
                    "return_code": None,
                    "metadata": self.current_metadata,
                    "log": self.streamer_log,
                }
            else:
                # Process has terminated
                status = {
                    "running": False, # stopped
                    "return_code": poll,
                    "metadata": self.current_metadata,
                    "log": self.streamer_log,
                }
        else:
            status = {
                "running": False, # stopped
                "return_code": None,
                "metadata": self.current_metadata,
                "log": self.streamer_log,
            }
        return status

    def _start_idle_streamer(self):
        """
        Start an idle streamer process (ffmpeg)
        """
        vf = f"drawtext=fontfile=./font.ttc"
        vf += f":text='Youtube Streamer {VERSION_STRING}@{self.get_endpoint_string()} by kurashizu\nNo video playing | "
        vf += r"%{localtime}'"
        vf += f":x=(w-text_w)/2:y=(h-text_h)/2:fontsize=48:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=5,"
        vf += f"drawtext=fontfile=./font.ttc"
        vf += f":textfile='{self.watermark_playlist.name}':reload=1"
        vf += f":x=20:y=h-th-20:fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=2,"
        vf += "format=nv12,hwupload"
        command = ["ffmpeg",
            "-loglevel", "warning",
            "-init_hw_device", "vaapi=va:/dev/dri/renderD128",
            "-hwaccel", "vaapi",
            "-re",
            "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=30", # Black screen input
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", # Audio input
            "-vf", vf,
            "-c:v", "h264_vaapi", "-b:v", "1200k", "-maxrate", "1200k",
            "-bufsize", "2400k",
            "-r", f"{self.IDLE_STREAM_FPS}",
            "-g", f"{self.IDLE_STREAM_GOP}", "-keyint_min", f"{self.IDLE_STREAM_GOP}",
            "-c:a", "aac", "-b:a", "128k",
            "-f", "flv",
            self.RTMP_URL
        ]
        self.idle_streamer = subprocess.Popen(command,
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE)
        print(f"Idle streamer@{self.get_endpoint_string()} started with PID: {self.idle_streamer.pid}")
        # logging
        self.streamer_log = {
            "stdout": self.streamer_log["stdout"][-100:],
            "stderr": self.streamer_log["stderr"][-100:],
        }
        threading.Thread(target=self._thread_streamer_log_stdout, args=(self.idle_streamer.stdout, self.idle_streamer.stderr), daemon=True).start()
        threading.Thread(target=self._thread_streamer_log_stderr, args=(self.idle_streamer.stdout, self.idle_streamer.stderr), daemon=True).start()
        pass
        
    def _stop_idle_streamer(self):
        """
        Stop the idle streamer process
        """
        if self.idle_streamer:
            print(f"Stopping idle streamer@{self.get_endpoint_string()} with PID: {self.idle_streamer.pid}")
            self.idle_streamer.terminate()
            try:
                self.idle_streamer.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"Idle streamer@{self.get_endpoint_string()} with PID {self.idle_streamer.pid} did not terminate gracefully, killing.")
                self.idle_streamer.kill()
                self.idle_streamer.wait()
            self.idle_streamer = None
            print(f"Idle streamer@{self.get_endpoint_string()} stopped.")
        pass

    def _is_idle_streamer_running(self):
        """
        Check if the idle streamer process is running
        """
        if self.idle_streamer:
            return self.idle_streamer.poll() is None
        return False

if __name__ == "__main__":
    s = Streamer()
        
    # Example usage:
    # Add a video to the queue
    print(1111)
    time.sleep(20)
    print(2222222)
    s.add_to_queue(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=150", stream_bitrate="1200k")

    # Get the current queue
    print("Current Queue:", s.get_queue())

    while 1:
        time.sleep(1)