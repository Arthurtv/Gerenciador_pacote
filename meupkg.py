import json
import os
import zipfile
import shutil
import subprocess
import stat
import requests
from urllib.parse import urlparse

DB_PATH = "db.json"
INSTALL_DIR = "./installed/"

def load_db():
    if not os.path.exists(DB_PATH):
        return {}
    with open(DB_PATH, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=4)

def baixar_arquivo(url, destino):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(destino, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return destino
    except requests.RequestException as e:
        print(f"Erro ao baixar o arquivo: {e}")
        return None

def install(pkgfile):
    if pkgfile.startswith("http://") or pkgfile.startswith("https://"):
        nome_arquivo = os.path.basename(urlparse(pkgfile).path)
        temp_path = os.path.join("temp_downloads", nome_arquivo)
        os.makedirs("temp_downloads", exist_ok=True)
        pkgfile = baixar_arquivo(pkgfile, temp_path)
        if not pkgfile:
            return

    if not pkgfile.endswith(".mpkg.zip") and not pkgfile.endswith(".art"):
        print("Formato inválido. Use arquivos .mpkg.zip ou .art")
        return

    base_name = os.path.basename(pkgfile).replace(".mpkg.zip", "").replace(".art", "")
    try:
        name, version = base_name.split("-")
    except ValueError:
        print("Nome do arquivo inválido. Use o formato nome-versao.mpkg.zip ou .art")
        return

    install_path = os.path.join(INSTALL_DIR, name)
    if os.path.exists(install_path):
        print("Pacote já instalado.")
        return

    os.makedirs(install_path, exist_ok=True)
    try:
        with zipfile.ZipFile(pkgfile, 'r') as zip_ref:
            zip_ref.extractall(install_path)
    except zipfile.BadZipFile:
        print("Erro: o arquivo não é um ZIP válido.")
        return

    db = load_db()
    db[name] = {
        "type": "package",
        "version": version,
        "path": install_path
    }
    save_db(db)
    print(f"Pacote '{name}' instalado com sucesso.")

def handle_remove_readonly(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def remove(pkgname):
    db = load_db()
    if pkgname not in db:
        print("Pacote ou repositório não está instalado.")
        return

    path = db[pkgname]["path"]

    if os.path.exists(path):
        shutil.rmtree(path, onerror=handle_remove_readonly)
        print(f"Pasta '{path}' removida.")
    else:
        print(f"Pasta '{path}' não encontrada, removendo apenas do banco.")

    del db[pkgname]
    save_db(db)
    print(f"'{pkgname}' removido do banco de dados.")

def update(pkgfile):
    name_ver = os.path.basename(pkgfile).replace(".mpkg.zip", "").replace(".art", "")
    try:
        name, version = name_ver.split("-")
    except ValueError:
        print("Nome do arquivo inválido. Use o formato nome-versao.mpkg.zip")
        return
    db = load_db()
    if name not in db:
        print("Pacote não instalado, usando 'install'.")
        install(pkgfile)
    else:
        print("Removendo versão antiga...")
        remove(name)
        print("Instalando nova versão...")
        install(pkgfile)

def verificar_repo(url):
    try:
        subprocess.run(["git", "ls-remote", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def clone(repo_url, destino=None):
    if destino is None:
        destino = os.path.basename(repo_url).replace('.git', '')
    destino = os.path.join(INSTALL_DIR, destino)

    if os.path.exists(destino):
        print("Repositório já existe.")
        return
    
    if not verificar_repo(repo_url):
        print("Repositório inacessível ou inexistente.")
        return

    try:
        print(f"Clonando {repo_url} em {destino}...")
        subprocess.run(['git', 'clone', repo_url, destino], check=True)

        db = load_db()
        name = os.path.basename(destino)
        db[name] = {
            "type": "git",
            "url": repo_url,
            "path": destino
        }
        save_db(db)

        print("Clonagem concluída e registrada no banco de dados!")
    except subprocess.CalledProcessError as e:
        print(f"Erro ao clonar: {e}")

def listar():
    db = load_db()
    if not db:
        print("Nenhum pacote ou repositório instalado.")
        return

    print("Itens registrados no sistema:\n")
    for name, info in db.items():
        tipo = info.get("type", "package")
        if tipo == "git":
            print(f"[GIT] {name} -> {info['url']}")
        else:
            print(f"[PKG] {name} -> versão {info.get('version', 'desconhecida')}")

def mostrar_ajuda():
    print("""
Gerenciador de Pacotes - Comandos Disponíveis:

  install <arquivo|url>     Instala um pacote .mpkg.zip ou .art (local ou por URL)
  remove <nome>             Remove um pacote ou repositório instalado
  update <arquivo>          Atualiza um pacote com nova versão
  clone <url> [destino]     Clona um repositório Git para a pasta de instalação
  list                      Lista todos os pacotes e repositórios instalados
  self-update               Atualizar o gerenciador de pacote
  help                      Mostra esta mensagem de ajuda

Exemplos:
  python meupkg.py install pacotes/ola-1.0.mpkg.zip
  python meupkg.py install https://meusite.com/pkg/app-1.2.art
  python meupkg.py update pacotes/ola-2.0.mpkg.zip
  python meupkg.py clone https://github.com/usuario/repositorio.git
  python meupkg.py remove ola
""")

# Entrada principal
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        mostrar_ajuda()
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "install":
        install(sys.argv[2])
    elif cmd == "remove":
        remove(sys.argv[2])
    elif cmd == "update":
        update(sys.argv[2])
    elif cmd == "clone":
        if len(sys.argv) == 3:
            clone(sys.argv[2])
        elif len(sys.argv) == 4:
            clone(sys.argv[2], sys.argv[3])
        else:
            print("Uso: python meupkg.py clone <url> [destino]")
    elif cmd == "list":
        listar()
    elif cmd == "help":
        mostrar_ajuda()
    elif cmd == "self-update":
        url = "link do github"
        try:
            response = requests.get(url)
            response.raise_for_status()
            with open(__file__, "wb") as f:
                f.write(response.content)
            print("Gerenciador de pacotes atualizado com sucesso!")
        except Exception as e:
            print(f"Erro ao atualizar: {e}")
    else:
        print(f"Comando inválido: '{cmd}'\n")
        mostrar_ajuda()

