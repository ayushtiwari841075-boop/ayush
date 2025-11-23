from flask import Flask, request, render_template_string import requests import json import time import os

app = Flask(name)

------------------ PREMIUM HTML TEMPLATE ------------------

premium_html = """

<!DOCTYPE html><html>
<head>
    <title>AYUSH OSINT - Premium Phone Lookup</title>
    <style>
        body {
            font-family: Arial;
            background: #000000;
            color: #00ffcc;
            margin: 0;
            padding: 0;
            text-align: center;
        }
        .header {
            background: linear-gradient(90deg, #00ffaa, #0099ff);
            padding: 20px;
            color: black;
            font-size: 26px;
            font-weight: bold;
            box-shadow: 0px 0px 15px #00ffaa;
        }
        .box {
            width: 70%;
            margin: auto;
            background: #0d0d0d;
            padding: 25px;
            margin-top: 30px;
            border-radius: 12px;
            border: 1px solid #00ffaa;
            box-shadow: 0px 0px 15px #00ffaa;
        }
        input {
            width: 60%;
            padding: 12px;
            font-size: 18px;
            border-radius: 8px;
            border: none;
            outline: none;
        }
        button {
            padding: 12px 25px;
            background: #00ffaa;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            margin-top: 10px;
            cursor: pointer;
        }
        button:hover { background: #00ddaa; }
        .record {
            text-align: left;
            background: #001a1a;
            border: 1px solid #00ffaa;
            padding: 15px;
            margin-top: 20px;
            border-radius: 10px;
            box-shadow: 0px 0px 10px #00ffaa;
        }
        .error { color: red; font-size: 20px; }
    </style>
</head>
<body>
<div class="header">AYUSH PREMIUM OSINT - PHONE LOOKUP</div>
<p>Developer: <b>@ayush_jibot</b></p>
<div class="box">
    <form method="POST">
        <input type="text" name="number" placeholder="Enter Phone Number" required>
        <br>
        <button type="submit">SEARCH</button>
    </form>
</div>{% if records %}

<h2>🔍 Lookup Result</h2>
{% for r in records %}
<div class="record">
    <p><b>👤 Name:</b> {{ r.get('name','N/A') }}</p>
    <p><b>📱 Mobile:</b> {{ r.get('mobile','N/A') }}</p>
    <p><b>👨 Father:</b> {{ r.get('fname','N/A') }}</p>
    <p><b>📞 Alt Number:</b> {{ r.get('alt','N/A') }}</p>
    <p><b>🏠 Address:</b> {{ r.get('address','N/A') }}</p>
    <p><b>🆔 Aadhaar:</b> {{ r.get('id','N/A') }}</p>
    <p><b>🌐 Circle:</b> {{ r.get('circle','N/A') }}</p>
</div>
{% endfor %}
{% endif %}{% if error %}

<p class="error">{{ error }}</p>
{% endif %}</body>
</html>
"""------------------ DATA FETCH FUNCTION ------------------

def fetch_number_info(number): url = f"https://vippanels.x10.mx/numapi.php?action=api&key=month&term={number}" try: response = requests.get(url, timeout=10) if response.status_code == 200: return response.json() return None except: return None

------------------ FLASK ROUTE ------------------

@app.route('/', methods=['GET','POST']) def index(): if request.method == 'POST': number = request.form.get('number')

if not number.isdigit() or len(number) < 10:
        return render_template_string(premium_html, error="Invalid number! Must be 10 digits.")

    data = fetch_number_info(number)

    if not data or 'data' not in data or not data['data']:
        return render_template_string(premium_html, error="No data found for this number.")

    return render_template_string(premium_html, records=data['data'])

return render_template_string(premium_html)

------------------ RUN SERVER ------------------

if name == 'main': app.run(host='0.0.0.0', port=20753, debug=True)
