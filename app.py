from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3, joblib
from datetime import datetime

app = Flask(__name__)
app.secret_key = "heartcare_secret_key"

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        result TEXT,
        probability REAL,
        date TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

# ---------------- LOAD MODEL (SAFE) ----------------
try:
    model = joblib.load("model.pkl")
    scaler = joblib.load("scaler.pkl")
    print("✅ Model & Scaler loaded")
except Exception as e:
    print("❌ Model load error:", e)
    model = None
    scaler = None

# ---------------- HOME ----------------
@app.route("/")
def index():
    if "user_email" not in session:
        return redirect("/login")

    return render_template(
        "index.html",
        name=session.get("user_name", "User")
    )

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (request.form["email"], request.form["password"])
        )
        user = c.fetchone()
        conn.close()

        if user:
            session["user_name"] = user[1]
            session["user_email"] = user[2]
            return redirect("/")
        return "Invalid Login"

    return render_template("login.html")

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO users VALUES(NULL,?,?,?)",
            (request.form["name"], request.form["email"], request.form["password"])
        )
        conn.commit()
        conn.close()
        return redirect("/login")

    return render_template("register.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- PROFILE ----------------
@app.route("/profile")
def profile():
    if "user_email" not in session:
        return redirect("/login")

    return render_template(
        "profile.html",
        name=session.get("user_name"),
        email=session.get("user_email")
    )

# ---------------- EDIT PROFILE ----------------
@app.route("/edit-profile")
def edit_profile():
    if "user_email" not in session:
        return redirect("/login")

    return render_template(
        "edit_profile.html",
        name=session.get("user_name"),
        email=session.get("user_email")
    )

@app.route("/api/profile", methods=["POST"])
def api_profile():
    if "user_email" not in session:
        return jsonify(success=False), 401

    data = request.json
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute(
        "UPDATE users SET name=?, email=? WHERE email=?",
        (data["name"], data["email"], session["user_email"])
    )
    conn.commit()
    conn.close()

    session["user_name"] = data["name"]
    session["user_email"] = data["email"]
    return jsonify(success=True)

# ---------------- HEALTH HISTORY ----------------
@app.route("/health-history")
def health_history():
    if "user_email" not in session:
        return redirect("/login")

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute(
        "SELECT date, result, probability FROM history WHERE email=?",
        (session["user_email"],)
    )
    rows = c.fetchall()
    conn.close()

    return render_template("health_history.html", records=rows)

# ---------------- SETTINGS ----------------
@app.route("/settings")
def settings():
    if "user_email" not in session:
        return redirect("/login")

    return render_template("settings.html")

@app.route("/api/clear-history", methods=["POST"])
def clear_history():
    if "user_email" not in session:
        return jsonify(success=False), 401

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("DELETE FROM history WHERE email=?", (session["user_email"],))
    conn.commit()
    conn.close()
    return jsonify(success=True)

@app.route("/api/delete-account", methods=["POST"])
def delete_account():
    if "user_email" not in session:
        return jsonify(success=False), 401

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE email=?", (session["user_email"],))
    c.execute("DELETE FROM history WHERE email=?", (session["user_email"],))
    conn.commit()
    conn.close()
    session.clear()
    return jsonify(success=True)
#--------------PREDICT--------
@app.route("/predict", methods=["POST"])
def predict():
    if model is None or scaler is None:
        return jsonify(error="Model not loaded"), 500

    try:
        # SAFE input handling
        age = float(request.form.get("age", 0))
        sex = float(request.form.get("sex", 0))
        cp = float(request.form.get("cp", 0))
        trestbps = float(request.form.get("trestbps", 0))
        chol = float(request.form.get("chol", 0))
        fbs = float(request.form.get("fbs", 0))

        # Default ML values
        restecg = 0
        thalach = 150
        exang = 0
        oldpeak = 0
        slope = 1
        ca = 0
        thal = 1

        data = [[
            age, sex, cp, trestbps, chol, fbs,
            restecg, thalach, exang, oldpeak, slope, ca, thal
        ]]

        prob = model.predict_proba(scaler.transform(data))[0][1]
        probability = round(prob * 100, 2)

        if probability >= 70:
            result = "High Chance of Heart Disease"
        elif probability >= 40:
            result = "Medium Chance of Heart Disease"
        else:
            result = "Low Chance of Heart Disease"

        # SAFE session access
        user_email = session.get("user_email", "guest")

        # SAFE DB insert
        conn = sqlite3.connect("users.db", timeout=10)
        c = conn.cursor()
        c.execute(
            "INSERT INTO history VALUES(NULL,?,?,?,?)",
            (
                user_email,
                result,
                probability,
                datetime.now().strftime("%d-%m-%Y")
            )
        )
        conn.commit()
        conn.close()

        return jsonify(prediction=result, probability=probability)

    except Exception as e:
        print("❌ PREDICT ERROR:", e)
        return jsonify(error=str(e)), 500

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)

