import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

# Define as senhas em texto puro
passwords = ["senha123", "senha456"]

# Gera os hashes
hashed_passwords = stauth.hasher(passwords).generate()

# Configura os usuários
config = {
    'credentials': {
        'usernames': {
            'anavarela': {
                'email': 'anabarrosvarela@gmail.com',
                'name': 'Ana Maria Barros Varela',
                'password': hashed_passwords[0]
            },
            'juliaabreu': {
                'email': 'juliaabreu2002@gmail.com',
                'name': 'Julia Abreu',
                'password': hashed_passwords[1]
            }
        }
    },
    'cookie': {
        'expiry_days': 30,
        'key': 'some_signature_key',
        'name': 'some_cookie_name'
    }
}

# Salva o arquivo
with open('config.yaml', 'w') as file:
    yaml.dump(config, file, default_flow_style=False)

print("✓ Arquivo config.yaml criado com sucesso!")
print("\nCredenciais para login:")
print("\nUsuário 1:")
print("Username: anavarela")
print("Senha: senha123")
print("\nUsuário 2:")
print("Username: juliaabreu")
print("Senha: senha456") 