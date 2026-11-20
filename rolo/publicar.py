"""rolo print (etiqueta de cor) / rolo albums (pick label): exporta JPGs do digiKam e envia."""
import shlex
import shutil
import subprocess

from . import ficha as F
from .campos import TAG_AI, album_de, montar_quadros
from .ia import CAMPOS_KW, _vocabulario
from .util import (TAGS_PICK, pick, Erro, exif_gravar, exif_ler, imagens, ligado, para_jpg, precisa, rodar,
                   trava, versao_mais_recente)

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


def args_sem_ia(d, grupos, q):
    """Argumentos do exiftool que tiram de um JPG o que a IA gravou e ninguém revisou (foto com ai:generated):
    título e descrição (voltam ao do roll.yaml, se houver), as keywords com prefixo de grupo do tags.yaml e
    a própria ai:generated, nos quatro campos de keyword. d: EXIF do JPG lido com exif_ler(..., *CAMPOS_KW)."""
    titulo, desc = q.get("title") or "", q.get("description") or ""
    args = [f"-XMP-dc:Title={titulo}", f"-IPTC:ObjectName={titulo[:64]}",
            f"-XMP-dc:Description={desc}", f"-ImageDescription={desc}", f"-UserComment={desc}",
            f"-IPTC:Caption-Abstract={desc[:2000]}"]
    for campo in CAMPOS_KW:
        v = d.get(campo.split(":")[1]) or []
        atuais = [str(x) for x in v] if isinstance(v, list) else [str(v)]
        args += [f"-{campo}-={k}" for k in atuais
                 if k == TAG_AI or (":" in k and k.partition(":")[0] in grupos)]
    return args


def _remoto_gphotos(base, album):
    base = base if base.endswith((":", "/")) else base + "/"
    return f"{base}album/{album}"


def albums(cfg, eq, args):
    """Exporta as fotos ainda não enviadas, uma pasta por álbum, e envia uma única vez ao Immich e ao Google Photos."""
    pasta = cfg.resolver(args.folder)
    precisa("exiftool")
    fi = F.ler(pasta)
    rolo = fi["roll"]
    arqs = imagens(pasta)
    quadros = montar_quadros(fi, len(arqs))
    numero = {a: n for n, a in enumerate(arqs, 1)}
    modo = eq.conv.get("portfolio_pick")
    sel = para_portfolio(pasta, modo)
    if not sel:
        raise Erro(f"Nenhuma foto {'com pick aceita' if modo else 'não recusada'} em {cfg.relativo(pasta)}")
    hist = F.historico(pasta)
    enviadas = set((hist.get("albums") or {}).get("files") or []) | set((hist.get("portfolio") or {}).get("files") or [])
    novas = [a for a in sel if a.stem not in enviadas]
    if not novas:
        print(f"Álbuns: nada novo para enviar ({len(sel)} foto(s) já enviada(s)).")
        return
    por_album = {}
    for a in novas:
        por_album.setdefault(album_de(eq, rolo, numero[a], quadros[numero[a]]), []).append(a)

    compartilhar = ligado(rolo.get("share", True))
    immich = compartilhar and ligado(cfg["ROLO_IMMICH"])
    gphotos = compartilhar and ligado(cfg["ROLO_GPHOTOS"])
    destinos = [d for d, sim in (("Immich", immich), ("Google Photos", gphotos)) if sim]
    staging = cfg.outbox / "albuns" / "_staging" / pasta.name
    criterio = "pick aceita" if modo else "todas menos as recusadas"
    print(f"Álbuns ({criterio}): {len(novas)} foto(s) nova(s)"
          + (f", {len(sel) - len(novas)} já enviada(s)" if len(sel) > len(novas) else ""))
    grupos = None
    bloqueadas = sem_revisao = 0
    enviados = 0
    with trava(pasta):
        if staging.exists():
            shutil.rmtree(staging)
        for nome, fotos in por_album.items():
            print(f"\n{nome}  ({len(fotos)})")
            pasta_album = staging / nome
            pasta_album.mkdir(parents=True)
            for a in list(fotos):
                jpg = pasta_album / f"{a.stem}.jpg"
                exportar(a, jpg, None, 95)
                todos = _conferir(a, jpg)
                problemas = [p for p in todos if TAG_AI not in p]
                graves = [p for p in problemas if p.startswith("faltou")]
                bloquear = graves and not args.force
                if len(problemas) < len(todos) and not bloquear:  # original com ai:generated
                    if grupos is None:
                        try:
                            grupos = set(_vocabulario(cfg))
                        except Erro as e:
                            print(f"  [aviso] {e} Só a tag {TAG_AI} sai das keywords.")
                            grupos = set()
                    d = exif_ler([jpg], *CAMPOS_KW).get(str(jpg), {})
                    exif_gravar([(jpg, args_sem_ia(d, grupos, quadros[numero[a]]))])
                    problemas.append("IA não revisada: vai sem título, descrição e tags da IA")
                    sem_revisao += 1
                print(f"  {a.name}" + (f"  ⚠ {'; '.join(problemas)}" if problemas else "  ✓ EXIF completo"))
                if bloquear:
                    jpg.unlink()
                    fotos.remove(a)
                    bloqueadas += 1
        if bloqueadas:
            print(f"\n{bloqueadas} foto(s) não exportada(s) por EXIF incompleto (use --force).")
        if sem_revisao:
            print(f"{sem_revisao} foto(s) com {TAG_AI} saíram sem os campos da IA. Elas não serão reenviadas "
                  "depois da revisão.")
        if args.dry_run:
            print(f"\n(dry-run: JPGs em {cfg.relativo(staging)}, nada enviado nem registrado)")
            return
        if not compartilhar:
            print("\nroll.share: false → só exportando, sem enviar.")
        elif not destinos:
            print("\nNenhum destino configurado (ROLO_IMMICH e ROLO_GPHOTOS vazios): só exportando, sem registrar.")
        for nome, fotos in por_album.items():
            if not fotos:
                continue
            origem = staging / nome
            if immich:
                precisa("immich")
                print(f"  Immich: álbum {nome} …")
                rodar(["immich", "upload", "--album-name", nome, str(origem)])
            if gphotos:
                _enviar_rclone(origem, _remoto_gphotos(cfg["ROLO_GPHOTOS"], nome))
            final = cfg.outbox / "albuns" / nome
            final.mkdir(parents=True, exist_ok=True)
            for jpg in sorted(origem.iterdir()):
                shutil.move(str(jpg), str(final / jpg.name))
            enviados += bool(destinos)
            # registra álbum a álbum: se um envio falhar no meio, os já enviados não voltam.
            # Sem destino configurado (e share ligado) não registra: ligar um destino depois envia estas.
            if destinos or not compartilhar:
                F.registrar(pasta, "albums", fotos, unir=True, albuns={nome: fotos})
            print(f"  {len(fotos)} foto(s) → {cfg.relativo(final)}")
    shutil.rmtree(staging, ignore_errors=True)
    print("Pronto." + (f" Enviado para: {', '.join(destinos)}." if enviados else ""))


def reindexar_photoprism(cfg, pasta):
    modelo = cfg["ROLO_PHOTOPRISM_INDEX_CMD"]
    if not modelo:
        print("  PhotoPrism: ROLO_PHOTOPRISM_INDEX_CMD não configurado (reindexação automática dele vale).")
        return
    cmd = modelo.replace("{folder}", shlex.quote(str(cfg.relativo(pasta))))
    print(f"  PhotoPrism: {cmd}")
    if subprocess.run(cmd, shell=True).returncode != 0:
        print("  [aviso] reindexação do PhotoPrism falhou")
