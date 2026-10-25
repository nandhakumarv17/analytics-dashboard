# Let's write a python script to syntactically check our latest app.py code for any errors
code_snippet = """
import os
import io
import json
import re
import traceback
from datetime import datetime
from flask import Flask, request, render_template_string, send_file, jsonify, redirect, url_for
import pandas as pd
import numpy as np

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

UPLOAD_DIR = "/tmp/dashboard_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATA_FILE_PATH = os.path.join(UPLOAD_DIR, "shared_data.pkl")
"""
try:
    compile(code_snippet, '<string>', 'exec')
    print("Syntax check passed for snippet")
except Exception as e:
    print("Syntax error:", e)
