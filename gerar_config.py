import streamlit_authenticator as stauth
import yaml

# Configurar credenciais
credentials = {
    "usernames": {
        "anavarela": {
            "name": "Ana Maria Barros Varela",
            "email": "anabarrosvarela@gmail.com",
            "password": "123456"  # será hasheada
        },
        "juliaabreu": {
            "name": "Julia Abreu",
            "email": "juliaabreu2002@gmail.com",
            "password": "123456"  # será hasheada
        }
    }
}

# Gerar hashes das senhas
hashed_passwords = stauth.Hasher(
    [credentials["usernames"][username]["password"] 
     for username in credentials["usernames"]]
).generate()

# Atualizar senhas com hashes
for (username, hashed_pw) in zip(credentials["usernames"], hashed_passwords):
    credentials["usernames"][username]["password"] = hashed_pw

# Configuração completa
config = {
    "credentials": credentials,
    "cookie": {
        "expiry_days": 30,
        "key": "abcdef",  # chave para cookie
        "name": "fatura_auth"
    }
}

# Salvar configuração
with open("config.yaml", "w") as file:
    yaml.dump(config, file)

print("✓ Arquivo config.yaml criado com sucesso!")
print("\nVocê pode fazer login com:")
print("Usuario: anavarela")
print("Senha: 123456")
print("\nou")
print("Usuario: juliaabreu")
print("Senha: 123456") 