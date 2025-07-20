#!/usr/bin/python3

import flask
import atexit
from streamer import Streamer
import time
from perfmonitor import PerfMon

RTMP_BASE_URL = "rtmp://xxx"

app = flask.Flask(__name__)
perfmon = PerfMon()
streamers = {
    "yt": Streamer(RTMP_BASE_URL=RTMP_BASE_URL, RTMP_STREAM_KEY="yt", perfmon=perfmon),
    "yt_aux1": Streamer(RTMP_BASE_URL=RTMP_BASE_URL, RTMP_STREAM_KEY="yt_aux1", perfmon=perfmon),
    "yt_aux2": Streamer(RTMP_BASE_URL=RTMP_BASE_URL, RTMP_STREAM_KEY="yt_aux2", perfmon=perfmon),
}

@atexit.register
def _atexit():
    for endpoint, streamer in streamers.items():
        streamer.stop_streamer()
        streamer._stop_idle_streamer()

@app.route('/ytapi/enqueue')
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
        stream_GOP=int(GOP) if GOP else 300,
        index=int(index) if index else None,
    )
    code = 200 if result["success"] else 400
    return flask.jsonify({
        "message": result["message"],
        "queue": [item["title"] for item in streamer.get_queue()],
    }), code

@app.route('/ytapi/dequeue')
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

@app.route('/ytapi/status')
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

    output += f"Version: {streamer.version}\n"
    output += f"Performance: {perfmon.get_performance_string()}\n"
    output += f"Current Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n"

    output += "\n".join(result["log"]["stdout"])
    if result["log"]["stderr"]:
        output += "\n--- ERRORS ---\n" + "\n".join(
            l for l in result["log"]["stderr"] if "Failed to update header" not in l
        )

    if len(output) > 1_000_000:
        streamer.stop_streamer()
        output = "Output too large, process killed."
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

@app.route('/ytapi/terminate')
def terminate():
    endpoint = flask.request.args.get('endpoint')
    if not endpoint:
        return flask.jsonify({"message": "No endpoint provided."}), 400
    if endpoint not in streamers:
        return flask.jsonify({"message": "Invalid endpoint."}), 400
    streamer = streamers[endpoint]
    
    streamer.stop_streamer()
    return flask.jsonify({"message": "Terminated."})

app.run(debug=True, host='0.0.0.0', port=8083, use_reloader=False)
