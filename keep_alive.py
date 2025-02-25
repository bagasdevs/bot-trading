
from flask import Flask
from threading import Thread
import logging

app = Flask('')
logging.basicConfig(level=logging.INFO)

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    try:
        app.run(host='0.0.0.0', port=8080)
    except Exception as e:
        logging.error(f"Error in web server: {e}")

def keep_alive():
    try:
        t = Thread(target=run, daemon=True)
        t.start()
        logging.info("Web server started successfully")
    except Exception as e:
        logging.error(f"Error starting web server: {e}")
