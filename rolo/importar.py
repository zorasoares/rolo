"""rolo import: pasta, nomes, formato e EXIF base. Rápido, para classificar logo em seguida."""
import collections
import datetime as dt
import shutil
from pathlib import Path

from . import ficha as F
from .campos import args_base, args_quadro, ler_data
from .util import (MESES, Erro, chave_natural, confirmar, escolher, exif_gravar, exif_ler, imagens,
                   interativo, perguntar, precisa, rodar, slug, trava)


def nome_pasta(eq, data, camera, filme, titulo):
    partes = [data.strftime("%Y%m%d"), camera]
    if not eq.digital(camera):
        partes.append(filme)
    partes.append(slug(titulo))
    return "-".join(partes)


def destino_pasta(cfg, eq, data, camera, filme, titulo):
    mes = f"{data.month:02d}-{MESES[data.month - 1]}"
    return cfg.root / str(data.year) / mes / nome_pasta(eq, data, camera, filme, titulo)


def data_mais_comum(arquivos):
    """Data mais frequente no EXIF (digitais) ou na data de modificação (scans)."""
    datas = []
    try:
        for d in exif_ler(arquivos, "DateTimeOriginal").values():
            if d.get("DateTimeOriginal"):
                datas.append(str(d["DateTimeOriginal"])[:10].replace(":", "-"))
    except Erro:
        pass
    if not datas:
        datas = [dt.date.fromtimestamp(a.stat().st_mtime).isoformat() for a in arquivos]
    return collections.Counter(datas).most_common(1)[0][0] if datas else dt.date.today().isoformat()


def _menu(cfg, eq, args, sugestao):
    """Completa o que não veio por flag, escolhendo sempre da base de equipamentos."""
    if not args.inbox:
        pastas = sorted([p for p in cfg.inbox.iterdir() if p.is_dir() and imagens(p)],
                        key=lambda p: p.stat().st_mtime, reverse=True) if cfg.inbox.exists() else []
        if not pastas:
            raise Erro(f"Nenhuma pasta com imagens em {cfg.inbox}")
        args.inbox = escolher("Pasta de entrada:", [(p, f"{p.name}  ({len(imagens(p))} arquivos)") for p in pastas])
    if not args.camera:
        if sugestao.get("camera_text") and not sugestao.get("camera"):
            print(f"\n[Exif Notes] câmera '{sugestao['camera_text']}' não reconhecida na base")
        args.camera = escolher("Câmera:", [(k, v["name"]) for k, v in eq.cameras.items()], sugestao.get("camera"))
    if not eq.digital(args.camera) and not args.film:
        if sugestao.get("film_text") and not sugestao.get("film"):
            print(f"\n[Exif Notes] filme '{sugestao['film_text']}' não reconhecido na base")
        args.film = escolher("Filme:", [(k, f"{v['name']} (ISO {v['iso']})") for k, v in eq.films.items()],
                              sugestao.get("film"), extra="cadastrar novo") or eq.cadastrar_filme()
    lentes = eq.lentes_da(args.camera)
    if lentes and not eq.digital(args.camera) and not args.lens:
        args.lens = escolher("Lente padrão:", [(k, v["name"]) for k, v in lentes.items()])
    if not eq.digital(args.camera) and not args.iso:
        iso_filme = eq.filme(args.film)["iso"]
        iso = sugestao.get("iso") or iso_filme
        args.iso = perguntar(f"ISO do rolo (filme: {iso_filme})", iso, validar=int)
    if not eq.digital(args.camera) and args.reversed is None:
        arqs = imagens(args.inbox)
        args.reversed = escolher("Ordem dos scans:", [
            (False, f"normal: {arqs[0].name} = quadro 1"),
            (True, f"invertida: {arqs[-1].name} = quadro 1 (o lab escaneou do fim para o começo)"),
        ], padrao=False)
    if not args.date:
        args.date = perguntar("Data do rolo (AAAA-MM-DD)", sugestao.get("date") or data_mais_comum(imagens(args.inbox)))
    if not args.title:
        args.title = perguntar("Título", sugestao.get("title"))


def executar(cfg, eq, args):
    precisa("exiftool")
    sugestao = {}
    if args.exifnotes:
        sugestao = F.sugestoes_rolo(eq, F.ler_exifnotes(cfg.resolver(args.exifnotes, cfg.inbox)))
    if args.inbox:
        args.inbox = cfg.resolver(args.inbox, cfg.inbox)
        if not args.inbox.is_dir():
            raise Erro(f"Pasta não encontrada: {args.inbox}")
    if interativo():
        _menu(cfg, eq, args, sugestao)
    faltando = [n for n in ("inbox", "camera", "date", "title") if not getattr(args, n)]
    if args.camera and not eq.digital(args.camera) and not args.film:
        faltando.append("film")
    if faltando:
        raise Erro(f"Faltando: {', '.join('--' + f for f in faltando)} (ou rode num terminal para usar o menu)")

    eq.camera(args.camera)
    digital = eq.digital(args.camera)
    if not digital:
        eq.filme(args.film)
        if args.lens:
            eq.lente(args.lens)
        if sugestao.get("camera") and sugestao["camera"] != args.camera:
            print(f"[aviso] o Exif Notes diz câmera {sugestao['camera']}, você escolheu {args.camera}")
        if sugestao.get("film") and sugestao["film"] != args.film:
            print(f"[aviso] o Exif Notes diz filme {sugestao['film']}, você escolheu {args.film}")

    data = ler_data(args.date)
    origem = Path(args.inbox)
    arquivos = imagens(origem)
    if not arquivos:
        raise Erro(f"Nenhuma imagem em {origem}")
    invertido = bool(args.reversed) and not digital
    if invertido:
        arquivos.reverse()  # o último scan é o quadro 1: renomeia na ordem do filme
    destino = destino_pasta(cfg, eq, data, args.camera, args.film, args.title)
    prefixo = nome_pasta(eq, data, args.camera, args.film, args.title)[9:].lower()
    digitos = max(2, len(str(len(arquivos))))
    raws = [a for a in arquivos if a.suffix.lower() == ".orf"]
    # dentro de _inbox/ (inclusive scans soltos na raiz dela) os arquivos são movidos; fora, copiados
    mover = origem.resolve().is_relative_to(cfg.inbox.resolve())

    print(f"\n→ {cfg.relativo(destino)}/  ({len(arquivos)} arquivos)")
    print(f"  {prefixo}_{data:%Y%m%d}_{1:0{digitos}d}{arquivos[0].suffix.lower().replace('.orf', '.dng')}"
          f" … _{len(arquivos):0{digitos}d}")
    if invertido:
        print(f"  ordem invertida: _{1:0{digitos}d} ← {arquivos[0].name} … "
              f"_{len(arquivos):0{digitos}d} ← {arquivos[-1].name}")
    if not mover:
        print(f"  fora de _inbox/: os arquivos são copiados, os originais ficam em {cfg.relativo(origem)}")
    if raws:
        print(f"  {len(raws)} ORF serão convertidos para DNG (os ORF ficam em {cfg.relativo(origem)})")
    if destino.exists() and any(destino.iterdir()):
        raise Erro(f"{destino} já existe e não está vazia")
    if interativo() and not confirmar("Confirmar?"):
        raise Erro("Cancelado")
    if raws:
        precisa("dnglab")

    destino.mkdir(parents=True, exist_ok=True)
    with trava(destino):
        novos = []
        for i, a in enumerate(arquivos, 1):
            ext = ".dng" if a.suffix.lower() == ".orf" else a.suffix.lower().replace(".jpeg", ".jpg").replace(".tiff", ".tif")
            novo = destino / f"{prefixo}_{data:%Y%m%d}_{i:0{digitos}d}{ext}"
            if a.suffix.lower() == ".orf":
                rodar(["dnglab", "convert", str(a), str(novo)], capture_output=True)
            elif mover:
                shutil.move(a, novo)
            else:
                shutil.copy2(a, novo)
            novos.append((i, a.name, novo))
            print(f"\r  arquivos: {i}/{len(arquivos)}", end="", flush=True)
        print()

        rolo = {"folder": str(cfg.relativo(destino)), "camera": args.camera, "film": None if digital else args.film,
                "lens": args.lens, "date": data.strftime("%Y-%m-%d"),
                "iso": None if digital else int(args.iso or eq.filme(args.film)["iso"]),
                "title": args.title, "count": len(novos), "offset": 0,
                "scan_order": None if digital else ("reversed" if invertido else "normal")}
        base = args_base(eq, rolo)
        lotes = [(novo, base + [f"-XMP-xmpMM:PreservedFileName={orig}"] + args_quadro(eq, rolo, n, {}))
                 for n, orig, novo in novos]
        print("  gravando EXIF base…")
        exif_gravar(lotes)
        F.gravar(destino, {"roll": rolo})

    # só apaga subpastas de _inbox/ que ficaram vazias; nunca a própria _inbox/ nem uma pasta do usuário
    if mover and origem.resolve() != cfg.inbox.resolve() and origem.exists() and not any(origem.iterdir()):
        origem.rmdir()
    print(f"\nPronto: {cfg.relativo(destino)}")
    print("Próximo: classificar no digiKam → `rolo print " + str(cfg.relativo(destino)) + "`")
    if args.exifnotes:
        print(f"Depois:  rolo sheet {cfg.relativo(destino)} --exifnotes {args.exifnotes}")
    return destino
