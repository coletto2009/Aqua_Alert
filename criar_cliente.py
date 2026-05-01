import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("banco.db")
cur = conn.cursor()

nome = "Cliente Teste"
email = "cliente@example.com"
senha = generate_password_hash("123456")

cur.execute("INSERT INTO clientes (nome, email, senha) VALUES (?, ?, ?)", (nome, email, senha))
conn.commit()
conn.close()

print("✅ Cliente criado!")
