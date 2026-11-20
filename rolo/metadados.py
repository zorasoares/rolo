"""rolo sheet (monta o roll.yaml com o Exif Notes) e rolo apply (grava a ficha nos arquivos)."""
from . import ficha as F
from .campos import args_base, args_quadro, montar_quadros, quadro_do_arquivo
from .util import Erro, escolher, exif_gravar, imagens, interativo, trava


def _pasta(cfg, caminho):
    pasta = cfg.resolver(caminho)
    if not pasta.is_dir():
        raise Erro(f"Pasta não encontrada: {caminho}")
    return pasta


def ficha(cfg, eq, args):
    pasta = _pasta(cfg, args.folder)
    fi = F.ler(pasta)
    if args.offset is not None:
        fi["roll"]["offset"] = args.offset
    antes = bool(fi["roll"].get("files_reversed"))
    ordem_arquivos(fi, pasta, args.reversed)
    if antes != bool(fi["roll"].get("files_reversed")) and not args.exifnotes:
        total = fi["roll"]["count"]
        for q in fi["frames"]:
            if q.get("source") == "exifnotes":
                q["n"] = total + 1 - int(q["n"])
    if args.exifnotes:
        en = F.ler_exifnotes(cfg.resolver(args.exifnotes, cfg.inbox))
        sug = F.sugestoes_rolo(eq, en)
        rolo = fi["roll"]
        if sug.get("camera") and sug["camera"] != rolo["camera"]:
            print(f"[aviso] Exif Notes: câmera {sug['camera']} ≠ rolo {rolo['camera']} (vale a do rolo)")
        if sug.get("film") and sug["film"] != rolo.get("film"):
            print(f"[aviso] Exif Notes: filme {sug['film']} ≠ rolo {rolo.get('film')} (vale o do rolo)")
        novos = F.quadros_exifnotes(eq, en, rolo, args.dates)
        fora = [q["n"] for q in novos if not 1 <= q["n"] <= rolo["count"]]
        if fora:
            print(f"[aviso] quadros do Exif Notes fora do rolo (1–{rolo['count']}): {fora}. "
                  "Se o lab numerou diferente, use --offset.")
        # substitui os do Exif Notes, mantém os manuais/skill
        fi["frames"] = [q for q in fi["frames"] if q.get("source") != "exifnotes"] + novos
    F.gravar(pasta, fi)
    resumo(fi)
    print(f"\nFicha: {cfg.relativo(F.caminho(pasta))}")
    print("Complete locais/lentes com a skill roll-sheet (ou à mão) e rode `rolo apply`.")


def ordem_arquivos(fi, pasta, invertido):
    """Define roll.files_reversed. Sem flag, pergunta só se o import não registrou a ordem dos scans."""
    rolo = fi["roll"]
    if invertido is None and "scan_order" not in rolo and "files_reversed" not in rolo:
        arqs = imagens(pasta)
        if not interativo() or not arqs:
            print("[aviso] a ficha não diz a ordem dos scans. Se o último arquivo for o quadro 1, "
                  "rode de novo com --reversed (ou --no-reversed para registrar que está normal).")
            return
        invertido = escolher("Ordem dos arquivos desta pasta:", [
            (False, f"normal: {arqs[0].name} = quadro 1"),
            (True, f"invertida: {arqs[-1].name} = quadro 1 (o lab escaneou do fim para o começo)"),
        ], padrao=False)
    if invertido is None:
        return
    if invertido and rolo.get("scan_order") == "reversed" and not rolo.get("files_reversed"):
        print("[aviso] o import já renomeou estes scans na ordem do filme (scan_order: reversed). "
              "Marcando como invertidos de novo, como pedido.")
    if invertido:
        rolo["files_reversed"] = True
    else:
        rolo.pop("files_reversed", None)
    rolo.setdefault("scan_order", "reversed" if invertido else "normal")


def resumo(fi):
    total = fi["roll"]["count"]
    q = montar_quadros(fi, total)
    en = sorted(n for n, d in q.items() if "exifnotes" in d["_source"].values())
    sem_local = [n for n, d in q.items() if d.get("lat") is None]
    sem_desc = [n for n, d in q.items() if not d.get("description")]
    print(f"\nExif Notes:    {len(en)}/{total} quadros {_faixas(en)}")
    print(f"Sem local:     {len(sem_local)} {_faixas(sem_local)}")
    print(f"Sem descrição: {len(sem_desc)} {_faixas(sem_desc)}  (→ `rolo ai`)")


def _faixas(nums):
    if not nums:
        return ""
    partes, ini, ant = [], nums[0], nums[0]
    for n in nums[1:] + [None]:
        if n is not None and n == ant + 1:
            ant = n
            continue
        partes.append(f"{ini}" if ini == ant else f"{ini}-{ant}")
        if n is not None:
            ini = ant = n
    return "(" + ", ".join(partes) + ")"


def aplicar(cfg, eq, args):
    pasta = _pasta(cfg, args.folder)
    fi = F.ler(pasta)
    rolo = fi["roll"]
    arquivos = imagens(pasta)
    if len(arquivos) != rolo["count"]:
        print(f"[aviso] a ficha diz {rolo['count']} quadros, a pasta tem {len(arquivos)} arquivos")
    quadros = montar_quadros(fi, len(arquivos))
    base = args_base(eq, rolo)
    lotes = [(a, base + args_quadro(eq, rolo, quadro_do_arquivo(rolo, n), quadros[n]))
             for n, a in enumerate(arquivos, 1)]
    if args.dry_run:
        for a, ar in lotes[: args.show]:
            print(f"\n{a.name}\n  " + "\n  ".join(ar))
        print(f"\n(dry-run: {len(lotes)} arquivos, nada gravado)")
        return
    with trava(pasta):
        exif_gravar(lotes)
        F.registrar(pasta, "apply")
    resumo(fi)
    print(f"\nGravado em {len(lotes)} arquivos. Nota e etiquetas do digiKam foram preservadas.")
