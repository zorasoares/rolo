"""rolo print (etiqueta de cor) / rolo portfolio (pick label): exporta JPGs do digiKam e envia."""
import shlex
import shutil
import subprocess

from . import ficha as F
from .campos import TAG_AI
from .util import (TAGS_PICK, pick, Erro, exif_ler, imagens, para_jpg, precisa, rodar, trava, versao_mais_recente)

CORES = {"red": "Red", "orange": "Orange", "yellow": "Yellow", "green": "Green", "blue": "Blue",
         "purple": "Magenta", "gray": "Gray", "grey": "Gray", "black": "Black", "white": "White",
         "vermelho": "Red", "laranja": "Orange", "amarelo": "Yellow", "verde": "Green", "azul": "Blue",
         "magenta": "Magenta", "roxo": "Magenta", "cinza": "Gray", "preto": "Black", "branco": "White"}
DIGIKAM_ID = {"1": "Red", "2": "Orange", "3": "Yellow", "4": "Green", "5": "Blue", "6": "Magenta",
              "7": "Gray", "8": "Black", "9": "White"}

# Tags copiadas do original para o JPG exportado (sem tags técnicas de DNG/TIFF e sem Orientation,
# porque a versão editada pode já estar girada).
COPIAR = ["-IFD0:Make", "-IFD0:Model", "-IFD0:Artist", "-IFD0:Copyright", "-IFD0:ImageDescription",
          "-ExifIFD:all", "-GPS:all", "-XMP:all", "-IPTC:all", "--Orientation", "--XMP-tiff:all",
          "--XMP-crs:all", "--XMP-xmpMM:all"]

OBRIGATORIOS = ["Make", "Model", "Artist", "Copyright", "DateTimeOriginal", "Description"]


def _cor(etiqueta):
    return CORES.get(etiqueta.lower(), etiqueta.capitalize())


def selecionadas(pasta, etiqueta):
    """Originais da pasta com a etiqueta de cor (xmp:Label ou digiKam:ColorLabel)."""
    cor = _cor(etiqueta)
    arquivos = imagens(pasta)
    dados = exif_ler(arquivos, "XMP-xmp:Label", "XMP-digiKam:ColorLabel")
    sel = []
    for a in arquivos:
        d = dados.get(str(a), {})
        rotulo = str(d.get("Label", "")).capitalize()
        dk = DIGIKAM_ID.get(str(d.get("ColorLabel", "")))
        if cor in (rotulo, dk):
            sel.append(a)
    return sel


def para_portfolio(pasta, modo):
    """Originais da pasta pela pick label do digiKam.
    modo None (padrão): tudo menos as recusadas. modo "accepted": só as aceitas."""
    if modo not in (None, "accepted"):
        raise Erro(f"conventions.portfolio_pick inválido: '{modo}' (use accepted ou remova a chave)")
    arquivos = imagens(pasta)
    dados = exif_ler(arquivos, *TAGS_PICK)
    picks = {a: pick(dados.get(str(a), {})) for a in arquivos}
    if modo == "accepted":
        return [a for a in arquivos if picks[a] == "accepted"]
    return [a for a in arquivos if picks[a] != "rejected"]


def exportar(original, destino, lado_maior, qualidade):
    fonte = versao_mais_recente(original)
    if fonte.suffix.lower() in (".jpg", ".jpeg") and not lado_maior:
        shutil.copy2(fonte, destino)  # já é JPG: sem recompressão
    else:
        para_jpg(fonte, destino, lado_maior=lado_maior, qualidade=qualidade)
    rodar(["exiftool", "-q", "-q", "-overwrite_original", "-charset", "filename=utf8",
           "-tagsFromFile", str(original), *COPIAR, str(destino)], capture_output=True)
    return fonte


def _enviar_rclone(local, remoto):
    precisa("rclone")
    print(f"  enviando para {remoto} …")
    rodar(["rclone", "copy", str(local), remoto, "--progress"])


def grafica(cfg, eq, args):
    pasta = cfg.resolver(args.folder)
    precisa("exiftool")
    sel = selecionadas(pasta, eq.conv.get("print_label", "green"))
    if not sel:
        raise Erro(f"Nenhuma foto com etiqueta {eq.conv.get('print_label', 'green')} em {cfg.relativo(pasta)}")
    saida = cfg.outbox / "print" / pasta.name
    saida.mkdir(parents=True, exist_ok=True)
    print(f"Gráfica: {len(sel)} foto(s) → {cfg.relativo(saida)}")
    for i, a in enumerate(sel, 1):
        fonte = exportar(a, saida / f"{a.stem}.jpg", None, 98)
        print(f"  [{i}/{len(sel)}] {fonte.name}")
    if args.no_upload or not cfg["ROLO_RCLONE_PRINT"]:
        print("Envio pulado.")
    else:
        _enviar_rclone(saida, f"{cfg['ROLO_RCLONE_PRINT'].rstrip('/')}/{pasta.name}")
        F.registrar(pasta, "print", sel)
    print("Pronto.")


def _conferir(original, jpg):
    """Compara o EXIF do JPG com o do original; devolve lista de problemas."""
    tags = OBRIGATORIOS + ["LensModel", "FNumber", "ExposureTime", "ISO", "GPSLatitude", "Subject", "Title"]
    d = exif_ler([original, jpg], *tags)
    o, j = d[str(original)], d[str(jpg)]
    problemas = [f"faltou {t}" for t in tags if o.get(t) not in (None, "") and j.get(t) in (None, "")]
    problemas += [f"sem {t}" for t in OBRIGATORIOS if o.get(t) in (None, "")]
    subj = o.get("Subject") or []
    if TAG_AI in (subj if isinstance(subj, list) else [subj]):
        problemas.append(f"descrição da IA ainda não revisada (tag {TAG_AI})")
    return problemas


def portfolio(cfg, eq, args):
    pasta = cfg.resolver(args.folder)
    precisa("exiftool")
    modo = eq.conv.get("portfolio_pick")
    sel = para_portfolio(pasta, modo)
    if not sel:
        raise Erro(f"Nenhuma foto {'com pick aceita' if modo else 'não recusada'} em {cfg.relativo(pasta)}")
    saida = cfg.outbox / "portfolio" / pasta.name
    lado = int(eq.conv.get("portfolio_size", 2048))
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    criterio = "pick aceita" if modo else "todas menos as recusadas"
    print(f"Portfólio ({criterio}): {len(sel)} foto(s) → {cfg.relativo(saida)} ({lado}px)")
    bloqueadas = 0
    with trava(pasta):
        for i, a in enumerate(sel, 1):
            jpg = saida / f"{a.stem}.jpg"
            exportar(a, jpg, lado, 90)
            problemas = _conferir(a, jpg)
            graves = [p for p in problemas if p.startswith("faltou") or TAG_AI in p]
            print(f"  [{i}/{len(sel)}] {a.name}" + (f"  ⚠ {'; '.join(problemas)}" if problemas else "  ✓ EXIF completo"))
            if graves and not args.force:
                jpg.unlink()
                bloqueadas += 1
    if bloqueadas:
        print(f"\n{bloqueadas} foto(s) não exportada(s) por EXIF incompleto ou IA não revisada (use --force).")
    if args.dry_run:
        print(f"\n(dry-run: JPGs em {cfg.relativo(saida)}, nada enviado)")
        return
    if not any(saida.iterdir()):
        return
    if cfg["ROLO_IMMICH_ALBUM"]:
        precisa("immich")
        print(f"  enviando para o Immich (álbum {cfg['ROLO_IMMICH_ALBUM']}) …")
        rodar(["immich", "upload", "--album-name", cfg["ROLO_IMMICH_ALBUM"], str(saida)])
    if cfg["ROLO_RCLONE_GPHOTOS"]:
        _enviar_rclone(saida, cfg["ROLO_RCLONE_GPHOTOS"])
    F.registrar(pasta, "portfolio", saida.iterdir())
    reindexar_photoprism(cfg, pasta)
    print("Pronto.")


def reindexar_photoprism(cfg, pasta):
    modelo = cfg["ROLO_PHOTOPRISM_INDEX_CMD"]
    if not modelo:
        print("  PhotoPrism: ROLO_PHOTOPRISM_INDEX_CMD não configurado (reindexação automática dele vale).")
        return
    cmd = modelo.replace("{folder}", shlex.quote(str(cfg.relativo(pasta))))
    print(f"  PhotoPrism: {cmd}")
    if subprocess.run(cmd, shell=True).returncode != 0:
        print("  [aviso] reindexação do PhotoPrism falhou")
