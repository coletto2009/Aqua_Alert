from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta


app = Flask(__name__, template_folder="templates")

# IMPORTANTE:
# Em produção, essa chave deve ficar em variável de ambiente.
app.secret_key = "chave-super-secreta"

# Mantém o usuário conectado por até 30 dias
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)


# =========================================================
# CONEXÃO COM MYSQL
# =========================================================

def conectar():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="agua_db"
    )


# =========================================================
# FUNÇÃO AUXILIAR - USUÁRIO LOGADO
# =========================================================



def usuario_logado():
    """
    Retorna o ID do usuário logado.
    Caso não exista usuário autenticado, retorna None.
    """
    return session.get("usuario_id")


def exigir_login():
    """
    Verifica se existe usuário autenticado.
    """
    if "usuario_id" not in session:
        return False

    return True


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    if exigir_login():
        return redirect(url_for("usuario"))

    return render_template("index.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        senha = request.form.get("senha", "")

        if not email or not senha:
            return render_template(
                "login.html",
                error="Preencha o email e a senha."
            )

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT id, senha, ativo
                FROM usuarios
                WHERE email = %s
                LIMIT 1
            """, (email,))

            user = cur.fetchone()

        finally:
            cur.close()
            conn.close()

        # Usuário não encontrado
        if not user:
            return render_template(
                "login.html",
                error="Email ou senha incorretos."
            )

        usuario_id = user[0]
        senha_hash = user[1]
        ativo = user[2]

        # Conta desativada
        if not ativo:
            return render_template(
                "login.html",
                error="Esta conta está desativada."
            )

        # Senha incorreta
        if not check_password_hash(senha_hash, senha):
            return render_template(
                "login.html",
                error="Email ou senha incorretos."
            )

        # ==========================================
        # SESSÃO DO USUÁRIO
        # ==========================================

        session.clear()

        # Mantém o usuário identificado
        session.permanent = True

        # Guarda o ID do usuário logado
        session["usuario_id"] = usuario_id

        return redirect(url_for("usuario"))

    return render_template("login.html")


# =========================================================
# CADASTRO
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not nome or not email or not senha:
            return render_template(
                "register.html",
                error="Preencha todos os campos."
            )

        if len(senha) < 4:
            return render_template(
                "register.html",
                error="A senha deve possuir pelo menos 4 caracteres."
            )

        senha_hash = generate_password_hash(senha)

        conn = conectar()
        cur = conn.cursor()

        try:

            # Verifica se o email já existe
            cur.execute("""
                SELECT id
                FROM usuarios
                WHERE email = %s
                LIMIT 1
            """, (email,))

            existente = cur.fetchone()

            if existente:
                return render_template(
                    "register.html",
                    error="Este email já está cadastrado."
                )

            # Cria usuário
            cur.execute("""
                INSERT INTO usuarios
                (
                    nome,
                    email,
                    senha
                )
                VALUES (%s, %s, %s)
            """, (
                nome,
                email,
                senha_hash
            ))

            conn.commit()

            usuario_id = cur.lastrowid

            # Cria sessão automaticamente
            session.clear()
            session["usuario_id"] = usuario_id

        except mysql.connector.Error as erro:

            conn.rollback()

            return render_template(
                "register.html",
                error=f"Erro ao criar conta: {erro}"
            )

        finally:
            cur.close()
            conn.close()

        return redirect(url_for("usuario"))

    return render_template("register.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# =========================================================
# PÁGINA DO USUÁRIO
# =========================================================

@app.route("/usuario")
def usuario():

    if "usuario_id" not in session:
        return redirect(url_for("login"))

    return render_template("usuario.html")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if not exigir_login():
        return redirect(url_for("login"))

    usuario_id = usuario_logado()

    conn = conectar()
    cur = conn.cursor()

    try:

        # -------------------------------------------------
        # CONSUMO DE HOJE
        # -------------------------------------------------

        cur.execute("""
            SELECT COALESCE(SUM(l.quantidade_litros), 0)
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
            AND DATE(l.medido_em) = CURDATE()
            AND s.ativo = TRUE
        """, (usuario_id,))

        resultado = cur.fetchone()

        consumo_hoje = float(resultado[0] or 0)

    finally:
        cur.close()
        conn.close()

    return render_template(
        "dashboard.html",
        consumo_hoje=consumo_hoje
    )


# =========================================================
# API - CONSUMO DIÁRIO
# =========================================================

@app.route("/api/consumo_diario")
def consumo_diario_api():

    if not exigir_login():
        return jsonify({
            "erro": "Usuário não autenticado."
        }), 401

    usuario_id = usuario_logado()

    conn = conectar()
    cur = conn.cursor(dictionary=True)

    try:

        cur.execute("""
            SELECT
                HOUR(l.medido_em) AS hora,
                SUM(l.quantidade_litros) AS total_litros
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
            AND DATE(l.medido_em) = CURDATE()
            AND s.ativo = TRUE
            GROUP BY HOUR(l.medido_em)
            ORDER BY hora ASC
        """, (usuario_id,))

        dados = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    # -----------------------------------------------------
    # Cria todas as 24 horas.
    #
    # Isso faz o gráfico mostrar também as horas sem
    # consumo, em vez de simplesmente desaparecerem.
    # -----------------------------------------------------

    valores_por_hora = {
        hora: 0.0
        for hora in range(24)
    }

    for registro in dados:

        hora = int(registro["hora"])

        valores_por_hora[hora] = float(
            registro["total_litros"] or 0
        )

    labels = [
        f"{hora:02d}:00"
        for hora in range(24)
    ]

    valores = [
        round(valores_por_hora[hora], 2)
        for hora in range(24)
    ]

    return jsonify({
        "labels": labels,
        "valores": valores
    })


# =========================================================
# API - CONSUMO SEMANAL
# =========================================================

@app.route("/api/consumo_semanal")
def consumo_semanal():

    if not exigir_login():
        return jsonify({
            "erro": "Usuário não autenticado."
        }), 401

    usuario_id = usuario_logado()

    conn = conectar()
    cur = conn.cursor(dictionary=True)

    try:

        cur.execute("""
            SELECT
                DATE(l.medido_em) AS dia,
                SUM(l.quantidade_litros) AS total_litros
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
              AND l.medido_em >= CURDATE() - INTERVAL 6 DAY
              AND l.medido_em < CURDATE() + INTERVAL 1 DAY
              AND s.ativo = TRUE
            GROUP BY DATE(l.medido_em)
            ORDER BY dia ASC
        """, (usuario_id,))

        dados = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    # -----------------------------------------------------
    # Organiza os resultados por data
    # -----------------------------------------------------

    consumo_por_dia = {}

    for registro in dados:

        dia = registro["dia"]

        if hasattr(dia, "strftime"):
            chave = dia.strftime("%Y-%m-%d")
        else:
            chave = str(dia)

        consumo_por_dia[chave] = float(
            registro["total_litros"] or 0
        )

    # -----------------------------------------------------
    # Gera exatamente os últimos 7 dias
    # -----------------------------------------------------

    labels = []
    valores = []

    hoje = date.today()

    nomes_dias = [
        "Seg",
        "Ter",
        "Qua",
        "Qui",
        "Sex",
        "Sáb",
        "Dom"
    ]

    for i in range(6, -1, -1):

        dia = hoje - timedelta(days=i)

        chave = dia.strftime("%Y-%m-%d")

        labels.append(
            f"{nomes_dias[dia.weekday()]} {dia.strftime('%d/%m')}"
        )

        valores.append(
            round(consumo_por_dia.get(chave, 0), 2)
        )

    return jsonify({
        "labels": labels,
        "valores": valores
    })


# =========================================================
# API - RESUMO DO DASHBOARD
# =========================================================

@app.route("/api/dashboard/resumo")
def dashboard_resumo():

    if not exigir_login():
        return jsonify({
            "erro": "Usuário não autenticado."
        }), 401

    usuario_id = usuario_logado()

    conn = conectar()
    cur = conn.cursor()

    try:

        # Consumo de hoje
        cur.execute("""
            SELECT COALESCE(SUM(l.quantidade_litros), 0)
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
              AND DATE(l.medido_em) = CURDATE()
              AND s.ativo = TRUE
        """, (usuario_id,))

        consumo_hoje = float(cur.fetchone()[0] or 0)

        # Consumo dos últimos 7 dias
        cur.execute("""
            SELECT COALESCE(SUM(l.quantidade_litros), 0)
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
              AND l.medido_em >= CURDATE() - INTERVAL 6 DAY
              AND l.medido_em < CURDATE() + INTERVAL 1 DAY
              AND s.ativo = TRUE
        """, (usuario_id,))

        consumo_semana = float(cur.fetchone()[0] or 0)

        # Quantidade de sensores ativos
        cur.execute("""
            SELECT COUNT(*)
            FROM sensores
            WHERE usuario_id = %s
              AND ativo = TRUE
        """, (usuario_id,))

        sensores_ativos = int(cur.fetchone()[0] or 0)

        # Quantidade de alertas não lidos
        cur.execute("""
            SELECT COUNT(*)
            FROM alertas a
            INNER JOIN sensores s
                ON s.id = a.sensor_id
            WHERE s.usuario_id = %s
              AND a.lido = FALSE
              AND a.descartado = FALSE
        """, (usuario_id,))

        alertas = int(cur.fetchone()[0] or 0)

    finally:
        cur.close()
        conn.close()

    return jsonify({
        "consumo_hoje": round(consumo_hoje, 2),
        "consumo_semana": round(consumo_semana, 2),
        "sensores_ativos": sensores_ativos,
        "alertas": alertas
    })


# =========================================================
# HISTÓRICO
# =========================================================

@app.route("/historico")
def historico():

    if "cliente_id" not in session:
        return redirect(url_for("login"))

    usuario_id = session["cliente_id"]

    conn = conectar()
    cur = conn.cursor(dictionary=True)

    try:

        # =====================================================
        # RESUMO DO CONSUMO POR DIA
        # =====================================================

        cur.execute("""
            SELECT
                DATE(l.medido_em) AS dia,
                SUM(l.quantidade_litros) AS total_litros,
                COUNT(l.id) AS quantidade_leituras
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
            GROUP BY DATE(l.medido_em)
            ORDER BY dia DESC
        """, (usuario_id,))

        resumo_diario = cur.fetchall()


        # =====================================================
        # TODAS AS LEITURAS DO USUÁRIO
        # =====================================================

        cur.execute("""
            SELECT
                l.id,
                l.sensor_id,
                s.nome AS sensor_nome,
                s.identificador,
                s.localizacao,
                l.fluxo_lpm,
                l.tds,
                l.pulsos,
                l.quantidade_litros,
                l.medido_em,
                l.recebido_em
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
            ORDER BY l.medido_em DESC
        """, (usuario_id,))

        leituras = cur.fetchall()


        # =====================================================
        # TOTAL GERAL
        # =====================================================

        cur.execute("""
            SELECT
                COALESCE(SUM(l.quantidade_litros), 0) AS total_litros,
                COUNT(l.id) AS total_leituras
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
        """, (usuario_id,))

        totais = cur.fetchone()

    finally:

        cur.close()
        conn.close()


    return render_template(
        "history.html",
        resumo_diario=resumo_diario,
        leituras=leituras,
        total_litros=totais["total_litros"],
        total_leituras=totais["total_leituras"]
    )
# =========================================================
# PÁGINAS DO SISTEMA
# =========================================================

@app.route("/history")
def history():

    if "usuario_id" not in session:
        return redirect(url_for("login"))

    usuario_id = session["usuario_id"]

    conn = conectar()
    cur = conn.cursor(dictionary=True)

    try:

        # ==========================================
        # RESUMO DO CONSUMO POR DIA
        # ==========================================

        cur.execute("""
            SELECT
                DATE(l.medido_em) AS dia,
                COALESCE(SUM(l.quantidade_litros), 0) AS total_litros,
                COUNT(l.id) AS quantidade_leituras
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
            GROUP BY DATE(l.medido_em)
            ORDER BY dia DESC
        """, (usuario_id,))

        resumo_diario = cur.fetchall()


        # ==========================================
        # TODAS AS LEITURAS DO USUÁRIO
        # ==========================================

        cur.execute("""
            SELECT
                l.id,
                l.sensor_id,
                s.nome AS sensor_nome,
                s.identificador,
                s.localizacao,
                l.fluxo_lpm,
                l.tds,
                l.pulsos,
                l.quantidade_litros,
                l.medido_em,
                l.recebido_em
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
            ORDER BY l.medido_em DESC
        """, (usuario_id,))

        leituras = cur.fetchall()


        # ==========================================
        # TOTAL GERAL
        # ==========================================

        cur.execute("""
            SELECT
                COALESCE(SUM(l.quantidade_litros), 0) AS total_litros,
                COUNT(l.id) AS total_leituras
            FROM leituras l
            INNER JOIN sensores s
                ON s.id = l.sensor_id
            WHERE s.usuario_id = %s
        """, (usuario_id,))

        totais = cur.fetchone()

    finally:

        cur.close()
        conn.close()


    return render_template(
        "history.html",
        resumo_diario=resumo_diario,
        leituras=leituras,
        total_litros=totais["total_litros"],
        total_leituras=totais["total_leituras"]
    )


@app.route("/profile")
def profile():

    if not exigir_login():
        return redirect(url_for("login"))

    return render_template("profile.html")


@app.route("/consumo")
def consumo():

    if not exigir_login():
        return redirect(url_for("login"))

    return render_template("consumo.html")


@app.route("/sensores", methods=["GET", "POST"])
def sensores():

    if not exigir_login():
        return redirect(url_for("login"))

    usuario_id = usuario_logado()

    conn = conectar()
    cur = conn.cursor(dictionary=True)

    try:

        # =================================================
        # CADASTRAR SENSOR
        # =================================================

        if request.method == "POST":

            nome = request.form.get("nome", "").strip()
            identificador = request.form.get("identificador", "").strip()
            codigo_dispositivo = request.form.get(
                "codigo_dispositivo", ""
            ).strip()
            localizacao = request.form.get(
                "localizacao", ""
            ).strip()

            if not nome or not identificador or not codigo_dispositivo:
                cur.close()
                conn.close()

                return render_template(
                    "sensores.html",
                    sensores=[],
                    erro="Preencha nome, identificador e código do dispositivo."
                )

            # Verifica se o identificador já pertence
            # a um sensor desse usuário
            cur.execute("""
                SELECT id
                FROM sensores
                WHERE usuario_id = %s
                  AND identificador = %s
                LIMIT 1
            """, (
                usuario_id,
                identificador
            ))

            sensor_existente = cur.fetchone()

            if sensor_existente:
                cur.close()
                conn.close()

                # Busca novamente os sensores
                conn = conectar()
                cur = conn.cursor(dictionary=True)

                cur.execute("""
                    SELECT
                        id,
                        identificador,
                        nome,
                        localizacao,
                        codigo_dispositivo,
                        ativo,
                        criado_em,
                        atualizado_em
                    FROM sensores
                    WHERE usuario_id = %s
                    ORDER BY criado_em DESC
                """, (usuario_id,))

                sensores_cadastrados = cur.fetchall()

                cur.close()
                conn.close()

                return render_template(
                    "sensores.html",
                    sensores=sensores_cadastrados,
                    erro="Esse identificador já está cadastrado na sua conta."
                )

            # Verifica se o código do dispositivo
            # já está sendo usado
            cur.execute("""
                SELECT id
                FROM sensores
                WHERE codigo_dispositivo = %s
                LIMIT 1
            """, (codigo_dispositivo,))

            codigo_existente = cur.fetchone()

            if codigo_existente:
                cur.close()
                conn.close()

                conn = conectar()
                cur = conn.cursor(dictionary=True)

                cur.execute("""
                    SELECT
                        id,
                        identificador,
                        nome,
                        localizacao,
                        codigo_dispositivo,
                        ativo,
                        criado_em,
                        atualizado_em
                    FROM sensores
                    WHERE usuario_id = %s
                    ORDER BY criado_em DESC
                """, (usuario_id,))

                sensores_cadastrados = cur.fetchall()

                cur.close()
                conn.close()

                return render_template(
                    "sensores.html",
                    sensores=sensores_cadastrados,
                    erro="Esse código de dispositivo já está cadastrado."
                )

            # Insere o novo sensor
            cur.execute("""
                INSERT INTO sensores
                (
                    usuario_id,
                    identificador,
                    nome,
                    localizacao,
                    codigo_dispositivo
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                usuario_id,
                identificador,
                nome,
                localizacao if localizacao else None,
                codigo_dispositivo
            ))

            conn.commit()

            # Redirecionamento após cadastro
            # evita duplicação ao atualizar a página
            cur.close()
            conn.close()

            return redirect(url_for("sensores"))


        # =================================================
        # LISTAR SENSORES DO USUÁRIO
        # =================================================

        cur.execute("""
            SELECT
                id,
                identificador,
                nome,
                localizacao,
                codigo_dispositivo,
                ativo,
                criado_em,
                atualizado_em
            FROM sensores
            WHERE usuario_id = %s
            ORDER BY criado_em DESC
        """, (usuario_id,))

        sensores_cadastrados = cur.fetchall()

    finally:
        try:
            cur.close()
        except:
            pass

        try:
            conn.close()
        except:
            pass

    return render_template(
        "sensores.html",
        sensores=sensores_cadastrados
    )


@app.route("/config")
def config():

    if not exigir_login():
        return redirect(url_for("login"))

    return render_template("config.html")


@app.route("/artigos")
def artigos():

    if not exigir_login():
        return redirect(url_for("login"))

    return render_template("artigo.html")


# =========================================================
# PÁGINAS PÚBLICAS
# =========================================================

@app.route("/dicas")
def dicas():

    return render_template("dicas.html")


@app.route("/sobre")
def sobre():

    return render_template("sobre.html")


@app.route("/artigosuser")
def artigosuser():

    return render_template("artigosuser.html")


# =========================================================
# INICIALIZAÇÃO
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)