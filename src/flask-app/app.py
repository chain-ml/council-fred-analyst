from flask import Flask, request, Response
from flask_cors import CORS
from subprocess import run
import os
from agent import AgentApp
import traceback
import logging
import time

logging.basicConfig(
    format="[%(asctime)s %(levelname)s %(threadName)s %(name)s:%(funcName)s:%(lineno)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S%z",
)


app = Flask(__name__)
CORS(app)
agent_app = None

logger = logging.getLogger("council")
logger.setLevel(logging.INFO)


# Create the custom logging handler
class MemoryHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.latest_log_message = None
        self.latest_output = ""

    def emit(self, record):
        log_message = self.format(record)
        if "Controller Message" in log_message:
            self.latest_log_message = log_message
        if "agent execution ended" in log_message:
            self.latest_log_message = self.latest_output


memory_handler = MemoryHandler()
logger.addHandler(memory_handler)


# Route to get the latest log message as an SSE stream
@app.route("/latest_log_stream")
def get_latest_log_stream():
    def generate_log_updates():
        while True:
            memory_handler.latest_log_message
            if memory_handler.latest_log_message:
                if "Controller Message" in memory_handler.latest_log_message:
                    memory_handler.latest_log_message += "."
                yield f"data: {memory_handler.latest_log_message}\n\n"
            time.sleep(1)

    return Response(generate_log_updates(), content_type="text/event-stream")


@app.route("/get_code")
def serve_code():
    if "code" in agent_app.controller._state:
        return agent_app.controller._state["code"], 200
    else:
        return "No code to display.", 200


@app.route("/reset", methods=["POST"])
def reset():
    global agent_app
    agent_app = AgentApp()
    agent_app.controller._state["code"] = None
    memory_handler.latest_log_message = "Ready."
    return "Ready!", 200


@app.route("/post_code", methods=["POST"])
def post_code():
    try:
        code = request.form.get("code")
        agent_app.controller._state["code"] = code
        print("CODE POSTED")
        return "Code posted!", 200
    except Exception as e:
        print("CODE NOT POSTED")
        print(e)
        return "Code was not posted", 500


# @app.route("/execute", methods=["POST"])
# def execute_code():
#     code = request.form.get("code")
#     agent_app.controller._state["code"] = code
#     try:
#         # Run the Python code as a subprocess
#         execution = run(["python", "-c", code], capture_output=True)
#         data = {
#             "stdout": execution.stdout.decode(),
#             "stderr": execution.stderr.decode(),
#         }
#         if execution.returncode == 0:
#             return data, 200
#         else:
#             return data, 404
#     except Exception as e:
#         return e, 500


@app.route("/handle_user_message", methods=["POST"])
def handle_user_message():
    try:
        message = request.form.get("message")
        agent_app.interact(message)
        agent_response = agent_app.context.chatHistory.last_agent_message.message
        memory_handler.latest_output = agent_response
        code = agent_app.controller._state["code"]
        return {"message": agent_response, "code": code}, 200
    except Exception as e:
        print(traceback.format_exc())
        return "Sorry, something went wrong!", 500


if __name__ == "__main__":
    agent_app = AgentApp()
    app.run(debug=True, use_reloader=False, threaded=True)
