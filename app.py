import io
import os

import pandas as pd
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB uploads


@app.route("/")
def index():
    return render_template_string(
        """
        <!doctype html>
        <html>
        <head>
            <title>Analytics Dashboard</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                form { margin-top: 20px; }
                input, button { padding: 10px; margin-top: 10px; }
            </style>
        </head>
        <body>
            <h1>Analytics Dashboard</h1>
            <p>Upload a CSV or Excel file to inspect it.</p>
            <form method="post" enctype="multipart/form-data" action="/upload">
                <input type="file" name="file" accept=".csv,.xlsx,.xls" required>
                <br>
                <button type="submit">Upload</button>
            </form>
        </body>
        </html>
        """
    )


@app.route("/upload", methods=["POST"])
def upload():
    uploaded = request.files.get("file")
    if uploaded is None or uploaded.filename == "":
        return jsonify({"error": "No file uploaded."}), 400

    filename = uploaded.filename.lower()
    content = uploaded.read()

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            return jsonify({"error": "Unsupported file type. Upload CSV or Excel."}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to read file: {exc}"}), 400

    preview = df.head(5).to_dict(orient="records")
    return jsonify({
        "rows": int(len(df)),
        "columns": list(df.columns),
        "preview": preview,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
