import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from yaml.dumper import SafeDumper
from getpass import getpass

def main():
    print("\n=== Configuração de Senhas para o App de Faturas ===\n")
    
    # Carregar configuração atual
    with open('config.yaml', 'r') as file:
        config = yaml.load(file, Loader=SafeLoader)
    
    # Lista de usuários para configurar
    users = ['anavarela', 'juliaabreu']
    
    for username in users:
        print(f"\nConfigurando senha para: {username}")
        password = getpass("Digite a senha: ")
        confirm_password = getpass("Confirme a senha: ")
        
        if password != confirm_password:
            print("As senhas não coincidem! Tente novamente.")
            continue
        
        if username in config['credentials']['usernames']:
            hashed_password = stauth.Hasher([password]).generate()[0]
            config['credentials']['usernames'][username]['password'] = hashed_password
            print(f"✓ Senha atualizada com sucesso para {username}")
    
    # Salvar configuração atualizada
    with open('config.yaml', 'w') as file:
        yaml.dump(config, file, Dumper=SafeDumper)
    
    print("\n✓ Configurações salvas em config.yaml")

if __name__ == "__main__":
    main() 