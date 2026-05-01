from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date   # <-- IMPORT AQUI
from datetime import datetime, timedelta

app = Flask(__name__, template_folder="templates")
app.secret_key = "chave-super-secreta"

# --- Conexão MySQL (WAMP) ---
def conectar():
    return mysql.connector.connect(
        host="localhost",
        user="root",        # ajuste se tiver senha
        password="",
        database="agua_db"
    )

# --- Rotas ---
@app.route("/")
def home():
    if "cliente_id" in session:
        return redirect(url_for("usuario"))
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]

        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT id, senha FROM usuarios WHERE email = %s", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user[1], senha):
            session["cliente_id"] = user[0]
            return redirect(url_for("usuario"))
        return render_template("login.html", error="Email ou senha incorretos.")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nome = request.form["nome"]
        email = request.form["email"]
        senha = request.form["senha"]

        if not all([nome, email, senha]):
            return render_template("register.html", error="Preencha todos os campos.")

        conn = conectar()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO usuarios (nome, email, senha) VALUES (%s, %s, %s)",
                (nome, email, generate_password_hash(senha))
            )
            conn.commit()
            cur.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            user = cur.fetchone()
            session["usuario_id"] = user[0]
        except Exception as e:
            conn.close()
            return render_template("register.html", error="Erro ao criar conta: " + str(e))

        conn.close()
        return redirect(url_for("usuario"))

    return render_template("register.html")

@app.route("/historico")
def historico():
    conn = conectar()
    cur = conn.cursor(dictionary=True)

    try:
        # 🔹 Agrupar total de litros por data
        cur.execute("""
            SELECT DATE(data) AS dia,
                   dispositivo_id,
                   SUM(quantidade_litros) AS total_litros,
                   MAX(atualizado_em) AS ultima_atualizacao
            FROM consumo_diario
            GROUP BY dia, dispositivo_id
            ORDER BY dia DESC
        """)
        dados = cur.fetchall()
    finally:
        conn.close()

    return jsonify(dados)




@app.route("/logout")
def logout():
    session.pop("cliente_id", None)
    return redirect(url_for("home"))

@app.route("/usuario")
def usuario():
    if "cliente_id" not in session:
        return redirect(url_for("login"))
    return render_template("usuario.html")

@app.route("/dashboard")
def dashboard():
    if "cliente_id" not in session:
        return redirect(url_for("login"))

    conn = conectar()
    cur = conn.cursor()

    hoje = date.today().strftime("%Y-%m-%d")

    cur.execute("""
        SELECT IFNULL(SUM(quantidade_litros), 0)
        FROM consumo_diario
        WHERE DATE(data) = %s
    """, (hoje,))
    consumo_hoje = cur.fetchone()[0]

    conn.close()

    return render_template("dashboard.html", consumo_hoje=consumo_hoje)

@app.route("/api/consumo_semanal")
def consumo_semanal():
    if "cliente_id" not in session:
        return redirect(url_for("login"))

    conn = conectar()
    cur = conn.cursor(dictionary=True)

    # últimos 7 dias (incluindo hoje)
    sete_dias_atras = (datetime.today() - timedelta(days=6)).strftime("%Y-%m-%d")

    cur.execute("""
        SELECT DATE(data) AS dia, SUM(quantidade_litros) AS total
        FROM consumo_diario
        WHERE DATE(data) >= %s
        GROUP BY DATE(data)
        ORDER BY dia ASC
    """, (sete_dias_atras,))
    
    dados = cur.fetchall()
    conn.close()

    # formata para labels e valores
    labels = [d["dia"].strftime("%d/%m") for d in dados]
    valores = [float(d["total"]) for d in dados]

    return jsonify({"labels": labels, "valores": valores})


@app.route("/api/consumo_diario")
def consumo_diario_api():
    if "cliente_id" not in session:
        return redirect(url_for("login"))

    conn = conectar()
    cur = conn.cursor(dictionary=True)

    hoje = datetime.today().strftime("%Y-%m-%d")

    # Pega todas as medições do dia atual
    cur.execute("""
        SELECT TIME(data) AS hora, quantidade_litros
        FROM consumo_diario
        WHERE DATE(data) = %s
        ORDER BY data ASC
    """, (hoje,))

    dados = cur.fetchall()
    conn.close()

    # Formata para Chart.js
    labels = [f"{d['hora'].seconds//3600:02d}:{(d['hora'].seconds//60)%60:02d}" for d in dados]
  # sempre retorna HH:MM
    valores = [float(d["quantidade_litros"]) for d in dados]

    print(dados)  
    return jsonify({"labels": labels, "valores": valores})



@app.route("/history")
def history():
    if "cliente_id" not in session:
        return redirect(url_for("login"))
    return render_template("history.html")

@app.route("/profile")
def profile():
    if "cliente_id" not in session:
        return redirect(url_for("login"))
    return render_template("profile.html")

@app.route("/consumo")
def consumo():
    if "cliente_id" not in session:
        return redirect(url_for("login"))
    return render_template("consumo.html")

@app.route("/sensores")
def sensores():
    if "cliente_id" not in session:
        return redirect(url_for("login"))
    return render_template("sensores.html")




@app.route("/config")
def config():
    if "cliente_id" not in session:
        return redirect(url_for("login"))
    return render_template("config.html")  # precisa criar config.html

@app.route("/artigos")
def artigos():
    if "cliente_id" not in session:
        return redirect(url_for("login"))
    return render_template("artigo.html")  


# Rotas tela index
@app.route("/dicas")
def dicas():
    return render_template("dicas.html")

@app.route("/sobre")
def sobre():
    return render_template("sobre.html")
    # Se quiser criar novos links como "Artigos" ou "Config"
@app.route("/artigosuser")
def artigosuser():
    return render_template("artigosuser.html")  # precisa criar artigo.html

if __name__ == "__main__":
    app.run(debug=True)
