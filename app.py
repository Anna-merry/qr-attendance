from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>Привет! Это система учёта посещаемости на QR-кодах!</h1>"

if __name__ == '__main__':
    app.run(debug=True)