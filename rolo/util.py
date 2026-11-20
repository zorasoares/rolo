"""Utilitários: menus no terminal, exiftool, lock, conversão de imagens, TOML."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

EXT_IMAGEM = {".tif", ".tiff", ".jpg", ".jpeg", ".dng", ".orf", ".png"}
MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
RE_VERSAO = re.compile(r"^(?P<base>.+)_(?:v(?P<n>\d+)|edited(?:_(?P<e>\d+))?)$")  # _vN do digiKam, _edited[_N] do RapidRAW


class Erro(Exception):
    """Erro esperado: mostrado ao usuário sem traceback."""


def ligado(valor):
    """Chave liga/desliga (config ou roll.yaml): "", false, off, no, 0 (sem diferenciar maiúsculas) = desligado."""
    return str(valor if valor is not None else "").strip().lower() not in ("", "false", "off", "no", "0")


def interativo():
    return sys.stdin.isatty() and sys.stdout.isatty()


def chave_natural(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", Path(p).name)]


def imagens(pasta, incluir_versoes=False):
    """Imagens de uma pasta em ordem natural. Versões editadas (_v1, _edited) ficam de fora por padrão."""
    arqs = [p for p in Path(pasta).iterdir() if p.is_file() and p.suffix.lower() in EXT_IMAGEM]
    if not incluir_versoes:
        arqs = [p for p in arqs if not RE_VERSAO.match(p.stem)]
    return sorted(arqs, key=chave_natural)


def versao_mais_recente(original):
    """Export _edited do RapidRAW (o _edited_N mais alto), senão a maior versão _vN do digiKam, senão o original."""
    melhores = []
    for p in original.parent.glob(f"{original.stem}_*"):
        m = RE_VERSAO.match(p.stem)
        if m and m["base"] == original.stem and p.suffix.lower() in EXT_IMAGEM:
            rank = (0, int(m["n"])) if m["n"] else (1, int(m["e"] or 0))
            melhores.append((rank, p.name, p))
    return max(melhores)[2] if melhores else original


# ---------------------------------------------------------------- menus

def escolher(titulo, opcoes, padrao=None, extra=None):
    """opcoes: lista de (valor, rótulo). extra: rótulo de uma opção adicional (retorna None)."""
    if not opcoes and not extra:
        raise Erro(f"Nenhuma opção para: {titulo}")
    print(f"\n{titulo}")
    idx_padrao = None
    for i, (valor, rotulo) in enumerate(opcoes, 1):
        marca = ""
        if valor == padrao:
            idx_padrao, marca = i, "  ← sugerido"
        print(f"  [{i}] {rotulo}{marca}")
    if extra:
        print(f"  [n] {extra}")
    while True:
        dica = f" [Enter = {idx_padrao}]" if idx_padrao else ""
        r = input(f"Escolha{dica}: ").strip().lower()
        if not r and idx_padrao:
            return opcoes[idx_padrao - 1][0]
        if extra and r == "n":
            return None
        if r.isdigit() and 1 <= int(r) <= len(opcoes):
            return opcoes[int(r) - 1][0]
        print("  opção inválida")


def perguntar(titulo, padrao=None, validar=None):
    while True:
        dica = f" [Enter = {padrao}]" if padrao not in (None, "") else ""
        r = input(f"{titulo}{dica}: ").strip()
        if not r and padrao not in (None, ""):
            r = str(padrao)
        if not r:
            print("  obrigatório")
            continue
        if validar:
            try:
                return validar(r)
            except ValueError as e:
                print(f"  {e}")
                continue
        return r


def confirmar(titulo, padrao=True):
    if not interativo():
        return padrao
    r = input(f"{titulo} [{'S/n' if padrao else 's/N'}]: ").strip().lower()
    return padrao if not r else r in ("s", "sim", "y")


def slug(texto):
    import unicodedata
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


# ---------------------------------------------------------------- comandos externos

def precisa(*programas):
    faltando = [p for p in programas if not shutil.which(p)]
    if faltando:
        raise Erro(f"Programa(s) não encontrado(s) nesta máquina: {', '.join(faltando)}. "
                   "Veja o README (seção Instalação).")


def rodar(cmd, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        raise Erro(f"Falhou ({r.returncode}): {' '.join(map(str, cmd))}")
    return r


def exif_ler(arquivos, *tags, numerico=False):
    """Lê tags com exiftool -j. Retorna {caminho: {tag: valor}}. numerico: valores crus (-n), sem formatação."""
    arquivos = [str(a) for a in arquivos]
    if not arquivos:
        return {}
    precisa("exiftool")
    cmd = ["exiftool", "-j", "-charset", "filename=utf8", *(["-n"] if numerico else []), *[f"-{t}" for t in tags]]
    r = subprocess.run(cmd + arquivos, capture_output=True, text=True)
    if not r.stdout.strip():
        raise Erro(f"exiftool não leu os arquivos: {r.stderr.strip()}")
    return {d["SourceFile"]: d for d in json.loads(r.stdout)}


TAGS_PICK = ("XMP-digiKam:PickLabel", "XMP-xmpDM:pick")


def pick(dados):
    """Pick label de uma foto lida com exif_ler(..., *TAGS_PICK): 'accepted', 'rejected', 'pending' ou None.
    digiKam grava PickLabel (1 recusada, 2 pendente, 3 aceita) e xmpDM:pick (-1, 0, 1)."""
    pl, dm = str(dados.get("PickLabel", "")), str(dados.get("Pick", ""))
    if pl == "3" or dm == "1":
        return "accepted"
    if pl == "1" or dm == "-1":
        return "rejected"
    if pl == "2":
        return "pending"
    return None


def exif_gravar(lotes, mostrar_erros=True):
    """lotes: lista de (arquivo, [args]). Uma única execução do exiftool com -execute entre os arquivos."""
    lotes = [(a, args) for a, args in lotes if args]
    if not lotes:
        return
    precisa("exiftool")
    with tempfile.NamedTemporaryFile("w", suffix=".args", encoding="utf-8", delete=False) as f:
        for arquivo, args in lotes:
            for a in args:
                f.write(a.replace("\n", " ") + "\n")
            f.write(f"{arquivo}\n-execute\n")
        argfile = f.name
    try:
        r = subprocess.run(["exiftool", "-@", argfile, "-common_args", "-overwrite_original", "-P",
                            "-charset", "utf8", "-charset", "filename=utf8", "-q", "-q"],
                           capture_output=True, text=True)
        if r.returncode != 0 or (r.stderr.strip() and mostrar_erros):
            msg = r.stderr.strip()
            if r.returncode != 0:
                raise Erro(f"exiftool falhou:\n{msg}")
            print(f"[aviso exiftool]\n{msg}")
    finally:
        os.unlink(argfile)


# ---------------------------------------------------------------- lock

@contextmanager
def trava(pasta):
    lock = Path(pasta) / ".rolo.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Erro(f"{lock} existe: outro `rolo` (PC ou servidor) está mexendo nesta pasta. "
                   "Se não estiver, apague o arquivo.")
    os.write(fd, f"{os.uname().nodename} pid {os.getpid()}\n".encode())
    os.close(fd)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


# ---------------------------------------------------------------- imagens

def para_jpg(origem, destino, lado_maior=None, qualidade=95):
    """Converte para JPG sRGB. Usa vips, ImageMagick ou darktable-cli (DNG), nessa ordem."""
    origem, destino = Path(origem), Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    raw = origem.suffix.lower() in (".dng", ".orf")
    if raw and shutil.which("darktable-cli"):
        cmd = ["darktable-cli", str(origem), str(destino), "--core", "--conf",
               f"plugins/imageio/format/jpeg/quality={qualidade}"]
        if lado_maior:
            cmd[4:4] = ["--width", str(lado_maior), "--height", str(lado_maior)]
        rodar(cmd, capture_output=True)
        return
    if shutil.which("vips"):
        alvo = f"{destino}[Q={qualidade},strip=false]"
        if lado_maior:
            rodar(["vips", "thumbnail", str(origem), alvo, str(lado_maior), "--size", "down",
                   "--export-profile", "srgb"], capture_output=True)
        else:
            rodar(["vips", "colourspace", str(origem), alvo, "srgb"], capture_output=True)
        return
    magick = shutil.which("magick") or shutil.which("convert")
    if magick:
        cmd = [magick, f"{origem}[0]", "-auto-orient", "-colorspace", "sRGB"]
        if lado_maior:
            cmd += ["-resize", f"{lado_maior}x{lado_maior}>"]
        rodar(cmd + ["-quality", str(qualidade), str(destino)], capture_output=True)
        return
    raise Erro("Nenhum conversor de imagem encontrado (instale libvips-tools ou imagemagick; "
               "para DNG digital, darktable).")
