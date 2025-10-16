#!/usr/bin/env python3
import json
import os
import zipfile
import shutil
import subprocess
import stat
import requests
from urllib.parse import urlparse
from datetime import datetime

# =========================
# CONFIGURAÇÕES GERAIS
# =========================
DB_PATH = "db.json"
REPOS_PATH = "repos.json"
INSTALL_DIR = "./installed/"

# =========================
# CORES E FORMATAÇÃO
# =========================
class Cores:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"

def log(msg, tipo="info"):
    hora = datetime.now().strftime("%H:%M:%S")
    prefixos = {
        "info": f"{Cores.CYAN}[INFO {hora}]",
        "ok": f"{Cores.GREEN}[OK {hora}]",
        "warn": f"{Cores.YELLOW}[AVISO {hora}]",
        "erro": f"{Cores.RED}[ERRO {hora}]",
        "git": f"{Cores.MAGENTA}[GIT {hora}]",
        "pkg": f"{Cores.BLUE}[PKG {hora}]"
    }
    print(f"{prefixos.get(tipo, '[INFO]')} {msg}{Cores.RESET}")

def banner():
    print(f"""{Cores.BLUE}{Cores.BOLD}
╔═════════════════════════════════════════════╗
║         🧩  meupkg - Gerenciador v1.0       ║
║        Desenvolvido por Arthurtv 💻         ║
╚═════════════════════════════════════════════╝
{Cores.RESET}""")

# =========================
# BANCO DE DADOS
# =========================
def load_db():
    if not os.path.exists(DB_PATH):
        return {}
    with open(DB_PATH, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=4)

# =========================
# INSTALAÇÃO DE PACOTES
# =========================
def baixar_arquivo(url, destino):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(destino, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        log(f"Arquivo baixado de {url}", "ok")
        return destino
    except requests.RequestException as e:
        log(f"Erro ao baixar o arquivo: {e}", "erro")
        return None

def install(pkgfile):
    log(f"Iniciando instalação de '{pkgfile}'", "pkg")

    if pkgfile.startswith(("http://", "https://")):
        nome_arquivo = os.path.basename(urlparse(pkgfile).path)
        temp_path = os.path.join("temp_downloads", nome_arquivo)
        os.makedirs("temp_downloads", exist_ok=True)
        pkgfile = baixar_arquivo(pkgfile, temp_path)
        if not pkgfile:
            return

    if not pkgfile.endswith((".mpkg.zip", ".art")):
        log("Formato inválido. Use arquivos .mpkg.zip ou .art", "erro")
        return

    base_name = os.path.basename(pkgfile).replace(".mpkg.zip", "").replace(".art", "")
    try:
        name, version = base_name.split("-")
    except ValueError:
        log("Nome inválido. Use nome-versao.mpkg.zip", "erro")
        return

    install_path = os.path.join(INSTALL_DIR, name)
    if os.path.exists(install_path):
        log("Pacote já instalado.", "warn")
        return

    os.makedirs(install_path, exist_ok=True)
    try:
        with zipfile.ZipFile(pkgfile, 'r') as zip_ref:
            zip_ref.extractall(install_path)
    except zipfile.BadZipFile:
        log("Erro: o arquivo não é um ZIP válido.", "erro")
        return

    db = load_db()
    db[name] = {
        "type": "package",
        "version": version,
        "path": install_path
    }
    save_db(db)
    log(f"Pacote '{name}' instalado com sucesso!", "ok")

# =========================
# REMOVER PACOTES
# =========================
def handle_remove_readonly(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def remove(pkgname):
    db = load_db()
    if pkgname not in db:
        log("Pacote ou repositório não encontrado.", "erro")
        return

    path = db[pkgname]["path"]

    if os.path.exists(path):
        shutil.rmtree(path, onerror=handle_remove_readonly)
        log(f"Pasta '{path}' removida.", "ok")
    else:
        log(f"Pasta '{path}' não encontrada, removendo do banco.", "warn")

    del db[pkgname]
    save_db(db)
    log(f"'{pkgname}' removido do sistema.", "ok")

# =========================
# ATUALIZAR PACOTE
# =========================
def update(pkgfile):
    log(f"Atualizando {pkgfile}...", "pkg")
    name_ver = os.path.basename(pkgfile).replace(".mpkg.zip", "").replace(".art", "")
    try:
        name, version = name_ver.split("-")
    except ValueError:
        log("Nome inválido. Use nome-versao.mpkg.zip", "erro")
        return
    db = load_db()
    if name not in db:
        log("Pacote não instalado. Instalando novo...", "warn")
        install(pkgfile)
    else:
        remove(name)
        install(pkgfile)

# =========================
# REPOSITÓRIOS GIT
# =========================
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
        log("Repositório já existe.", "warn")
        return

    if not verificar_repo(repo_url):
        log("Repositório inacessível ou inexistente.", "erro")
        return

    try:
        log(f"Clonando {repo_url} em {destino}...", "git")
        subprocess.run(['git', 'clone', repo_url, destino], check=True)

        db = load_db()
        name = os.path.basename(destino)
        db[name] = {
            "type": "git",
            "url": repo_url,
            "path": destino
        }
        save_db(db)

        log("Clonagem concluída e registrada no banco de dados!", "ok")
    except subprocess.CalledProcessError as e:
        log(f"Erro ao clonar: {e}", "erro")

# =========================
# LISTAGEM
# =========================
def listar():
    db = load_db()
    if not db:
        log("Nenhum pacote ou repositório instalado.", "warn")
        return

    print(f"\n{Cores.BOLD}{Cores.CYAN}Itens instalados:{Cores.RESET}")
    for name, info in db.items():
        tipo = info.get("type", "package")
        if tipo == "git":
            print(f"  🔗 {Cores.MAGENTA}[GIT]{Cores.RESET} {name} -> {info['url']}")
        else:
            print(f"  📦 {Cores.BLUE}[PKG]{Cores.RESET} {name} -> versão {info.get('version', 'desconhecida')}")
    print()

# =========================
# AJUDA
# =========================
def mostrar_ajuda():
    print(f"""{Cores.BOLD}{Cores.YELLOW}
Comandos disponíveis:
─────────────────────────────────────{Cores.RESET}
  install <arquivo|url>   → Instala um pacote .mpkg.zip ou .art
  remove <nome>           → Remove um pacote instalado
  update <arquivo>        → Atualiza um pacote
  clone <url> [destino]   → Clona um repositório Git
  list                    → Lista pacotes instalados
  add-repo <url>          → Adiciona um repositório
  remove-repo <url>       → Remove um repositório
  list-repos              → Mostra todos os repositórios
  self-update             → Atualiza o gerenciador
  help                    → Mostra esta ajuda
─────────────────────────────────────
Exemplos:
  meupkg install ola-1.0.mpkg.zip
  meupkg install https://meusite.com/pkg/app-1.2.art
  meupkg clone https://github.com/user/repo.git
{Cores.RESET}""")

# =========================
# MULTI-REPO SYSTEM
# =========================
def load_repos():
    if not os.path.exists(REPOS_PATH):
        return {"repos": []}
    with open(REPOS_PATH, "r") as f:
        return json.load(f)

def save_repos(repos):
    with open(REPOS_PATH, "w") as f:
        json.dump(repos, f, indent=4)

def add_repo(url):
    repos = load_repos()
    if url in repos["repos"]:
        log("Repositório já adicionado.", "warn")
        return
    if not verificar_repo(url):
        log("Repositório inacessível ou inexistente.", "erro")
        return
    repos["repos"].append(url)
    save_repos(repos)
    log("Repositório adicionado com sucesso.", "ok")

def remove_repo(url):
    repos = load_repos()
    if url not in repos["repos"]:
        log("Repositório não encontrado.", "erro")
        return
    repos["repos"].remove(url)
    save_repos(repos)
    log("Repositório removido com sucesso.", "ok")

def list_repos():
    repos = load_repos()
    if not repos["repos"]:
        log("Nenhum repositório adicionado.", "warn")
        return
    print(f"\n{Cores.BOLD}{Cores.CYAN}Repositórios registrados:{Cores.RESET}")
    for repo in repos["repos"]:
        print(f"  🔗 {repo}")
    print()

# =========================
# EXECUÇÃO PRINCIPAL
# =========================
if __name__ == "__main__":
    import sys
    banner()
    if len(sys.argv) < 2:
        mostrar_ajuda()
        sys.exit(1)

    cmd = sys.argv[1]

    try:
        if cmd == "install":
            install(sys.argv[2])
        elif cmd == "remove":
            remove(sys.argv[2])
        elif cmd == "update":
            update(sys.argv[2])
        elif cmd == "clone":
            clone(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        elif cmd == "list":
            listar()
        elif cmd == "add-repo":
            add_repo(sys.argv[2])
        elif cmd == "remove-repo":
            remove_repo(sys.argv[2])
        elif cmd == "list-repos":
            list_repos()
        elif cmd == "self-update":
            url = "https://raw.githubusercontent.com/Arthurtv/Gerenciador_pacote/main/meupkg.py"
            response = requests.get(url)
            response.raise_for_status()
            with open(__file__, "wb") as f:
                f.write(response.content)
            log("Gerenciador atualizado com sucesso!", "ok")
        elif cmd == "help":
            mostrar_ajuda()
        else:
            log(f"Comando inválido: '{cmd}'", "erro")
            mostrar_ajuda()
    except IndexError:
        log("Argumento ausente. Use 'help' para mais informações.", "erro")
