import bcrypt
import yaml
from getpass import getpass

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def main():
    print("Configuração de senhas para o app de faturas")
    print("-------------------------------------------")
    
    # Carregar configuração existente
    try:
        with open('config.yaml') as file:
            config = yaml.safe_load(file)
    except:
        config = {
            'credentials': {
                'usernames': {}
            },
            'cookie': {
                'expiry_days': 30,
                'key': 'some_signature_key',
                'name': 'fatura_auth'
            },
            'preauthorized': {
                'emails': []
            }
        }
    
    while True:
        username = input("\nDigite o nome de usuário (ou ENTER para sair): ").strip()
        if not username:
            break
            
        email = input("Digite o email: ").strip()
        name = input("Digite o nome completo: ").strip()
        password = getpass("Digite a senha: ")
        
        # Gerar hash da senha
        hashed_password = hash_password(password)
        
        # Adicionar ou atualizar usuário
        if 'credentials' not in config:
            config['credentials'] = {'usernames': {}}
        
        config['credentials']['usernames'][username] = {
            'email': email,
            'name': name,
            'password': hashed_password
        }
        
        # Adicionar email à lista de preautorizados
        if 'preauthorized' not in config:
            config['preauthorized'] = {'emails': []}
        if email not in config['preauthorized']['emails']:
            config['preauthorized']['emails'].append(email)
        
        print(f"\nUsuário {username} configurado com sucesso!")
    
    # Salvar configuração
    with open('config.yaml', 'w') as file:
        yaml.dump(config, file)
    
    print("\nConfigurações salvas em config.yaml")

if __name__ == "__main__":
    main() 