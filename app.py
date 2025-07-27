#!/usr/bin/python3

import flask
import atexit
from streamer import Streamer
import time
from perfmonitor import PerfMon
import json
import os

# Load configuration from config.json
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

# Get config values, allowing environment variables to override them
VERSION_STRING = config["version_string"]
RTMP_BASE_URL = config["rtmp"]["base_url"]
RTMP_STREAMS = config["rtmp"]["streams"]
PUBLIC_BASE_URL = config["server"]["public_base_url"]
DISTRIBUTORS = config["rtmp"]["distributors"]
LISTENING_ADDR = config["server"]["listening_addr"]
LISTENING_PORT = config["server"]["listening_port"]
YTDLP_COOKIE_FILE_YOUTUBE = config["yt-dlp"]["cookie_file"].get("youtube", None)
YTDLP_COOKIE_FILE_BILIBILI = config["yt-dlp"]["cookie_file"].get("bilibili", None)

app = flask.Flask(__name__, template_folder=os.path.dirname(os.path.abspath(__file__)))
perfmon = PerfMon()

streamers = { # Initialize streamers from config
    key: Streamer(
        RTMP_BASE_URL=RTMP_BASE_URL,
        RTMP_STREAM_KEY=key,
        perfmon=perfmon,
        version_string=VERSION_STRING,
        ytdlp_cookie_youtube=YTDLP_COOKIE_FILE_YOUTUBE,
        ytdlp_cookie_bilibili=YTDLP_COOKIE_FILE_BILIBILI,
        )
    for key in RTMP_STREAMS
}

@atexit.register
def _atexit():
    for endpoint, streamer in streamers.items():
        streamer.stop_streamer()
        streamer._stop_idle_streamer()

@app.route('/')
def index():
    return flask.render_template('streamer.html', version=VERSION_STRING, api_url=PUBLIC_BASE_URL, endpoints=RTMP_STREAMS, distributors=DISTRIBUTORS)

@app.route('/streamer/enqueue')
def enqueue():
    endpoint = flask.request.args.get('endpoint')
    if not endpoint:
        return flask.jsonify({"message": "No endpoint provided."}), 400
    if endpoint not in streamers:
        return flask.jsonify({"message": "Invalid endpoint."}), 400
    streamer = streamers[endpoint]

    url = flask.request.args.get('url')
    if not url:
        return flask.jsonify({"message": "No URL provided."}), 400
    
    bitrate = flask.request.args.get('bitrate')
    # limit bitrate < 10000k
    if bitrate:
        try:
            int_bitrate = int(bitrate.replace('k', ''))
        except ValueError:
            return flask.jsonify({"message": "Invalid bitrate format."}), 400
        if int_bitrate > 10000:
            return flask.jsonify({"message": "Bitrate too high. Maximum 10000k."}), 400
            
    audioOnly = flask.request.args.get('audioOnly')
    if audioOnly == "true":
        bitrate = "600k"
    FPS = flask.request.args.get('FPS')
    GOP = flask.request.args.get('GOP')
    index = flask.request.args.get('index')

    result = streamer.add_to_queue(
        url=url,
        stream_bitrate=bitrate if bitrate else "1200k",
        stream_audioOnly=audioOnly if audioOnly else False,
        stream_FPS=int(FPS) if FPS else 60,
        stream_GOP=int(GOP) if GOP else 120,
        index=int(index) if index else None,
    )
    code = 200 if result["success"] else 400
    return flask.jsonify({
        "message": result["message"],
        "queue": [item["title"] for item in streamer.get_queue()],
    }), code

@app.route('/streamer/dequeue')
def dequeue():
    endpoint = flask.request.args.get('endpoint')
    if not endpoint:
        return flask.jsonify({"message": "No endpoint provided."}), 400
    if endpoint not in streamers:
        return flask.jsonify({"message": "Invalid endpoint."}), 400
    streamer = streamers[endpoint]

    index = flask.request.args.get('index')
    
    result = streamer.remove_from_queue(int(index))
    code = 200 if result["success"] else 400
    return flask.jsonify({
        "message": result["message"],
        "queue": [item["title"] for item in streamer.get_queue()],
    }), code

@app.route('/streamer/status')
def status():
    endpoint = flask.request.args.get('endpoint')
    if not endpoint:
        return flask.jsonify({"message": "No endpoint provided."}), 400
    if endpoint not in streamers:
        return flask.jsonify({"message": "Invalid endpoint."}), 400
    streamer = streamers[endpoint]
    
    result = streamer.get_streamer_status()
    metadata = result["metadata"]

    if metadata:
        output = f"Playing: [{metadata['total_time']}s] [{'AudioOnly' if metadata['stream_audioOnly'] else metadata['stream_bitrate']}] {metadata['title']}\n"
    else:
        output = "No video playing.\n"

    output += f"Version: {streamer.version_string}\n"
    output += f"Performance: {perfmon.get_performance_string()}\n"
    output += f"Current Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n"

    output += "\n".join(result["log"]["stdout"])
    if result["log"]["stderr"]:
        output += "\n--- LOG ---\n" + "\n".join(
            l for l in result["log"]["stderr"] if "Failed to update header" not in l
        )

    if not output:
        output = "No output yet."

    code = 200
    # queue that includes formatted titles
    formatted_queue = [
        f"{i+1}. [{item['total_time']}s] [{'AudioOnly' if item['stream_audioOnly'] else item['stream_bitrate']}] {item['title']}"
        for i, item in enumerate(streamer.get_queue())
    ]
    return flask.jsonify({
        "runner": {
            "running": result["running"],
            "output": output,
            "code": result["return_code"],
        },
        "playlist": {
            "queue": formatted_queue,
            "size": len(formatted_queue),
        }
    }), code

@app.route('/streamer/terminate')
def terminate():
    endpoint = flask.request.args.get('endpoint')
    if not endpoint:
        return flask.jsonify({"message": "No endpoint provided."}), 400
    if endpoint not in streamers:
        return flask.jsonify({"message": "Invalid endpoint."}), 400
    streamer = streamers[endpoint]
    
    streamer.stop_streamer()
    return flask.jsonify({"message": "Terminated."})

app.run(debug=True, host=LISTENING_ADDR, port=LISTENING_PORT, use_reloader=False)
