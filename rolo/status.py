"""rolo status: em que etapa do fluxo cada rolo está.

Nada é marcado à mão: a etapa é deduzida do roll.yaml, do EXIF dos arquivos (pick, etiqueta, GPS,
ai:generated), do _outbox e do .rolo-history.yaml (envios de print/albums e último apply).
"""
from pathlib import Path

from . import ficha as F
from .campos import TAG_AI, args_base, args_quadro, montar_quadros, quadro_do_arquivo
from .manutencao import ignorada
from .metadados import _faixas
from .publicar import DIGIKAM_ID, _cor
from .util import TAGS_PICK, Erro, exif_ler, imagens, pick

OK, PULADO, PENDENTE = "ok", "pulado", "pendente"
NOME_COR = {"Red": "vermelha", "Orange": "laranja", "Yellow": "amarela", "Green": "verde", "Blue": "azul",
            "Magenta": "roxa", "Gray": "cinza", "Black": "preta", "White": "branca"}

# Tags gravadas pelo `rolo apply` que o digiKam não mexe: se diferem do roll.yaml, falta rodar o apply.
CONFERIR = ("GPSLatitude", "GPSLongitude", "DateTimeOriginal", "LensModel", "City", "State", "Country", "ImageNumber")
LER = (*TAGS_PICK, "XMP-xmp:Rating", "XMP-xmp:Label", "XMP-digiKam:ColorLabel", "XMP-dc:Description",
       "ImageDescription", "XMP-dc:Subject", "EXIF:GPSLatitude", "EXIF:GPSLongitude", "DateTimeOriginal",
       "LensModel", "City", "State", "Country", "ImageNumber")


class Etapa:
    def __init__(self, nome, estado, detalhe="", comando=None, lateral=False):
        self.nome, self.estado, self.detalhe, self.comando, self.lateral = nome, estado, detalhe, comando, lateral


def _igual(esperado, lido):
    if lido in (None, ""):
        return False
    try:
        return abs(float(esperado) - float(lido)) < 1e-5
    except ValueError:
        return str(esperado).strip() == str(lido).strip()


def _esperado(eq, rolo, n, q):
    """{tag: valor} que o `rolo apply` gravaria no arquivo n, só das tags de CONFERIR."""
    saida = {}
    for a in args_base(eq, rolo) + args_quadro(eq, rolo, quadro_do_arquivo(rolo, n), q):
        tag, _, valor = a[1:].partition("=")
        if tag in CONFERIR:
            saida[tag] = valor
    return saida


def _subject(d):
    s = d.get("Subject") or []
    return s if isinstance(s, list) else [s]


def avaliar(cfg, eq, pasta):
    """Lista de Etapa na ordem do fluxo, para uma pasta de rolo."""
    fi = F.ler(pasta)
    rolo = fi["roll"]
    hist = F.historico(pasta)
    rel = cfg.relativo(pasta)
    arqs = imagens(pasta)
    quadros = montar_quadros(fi, len(arqs))
    exif = exif_ler(arqs, *LER, numerico=True) if arqs else {}
    d = {a: exif.get(str(a), {}) for a in arqs}
    picks = {a: pick(d[a]) for a in arqs}
    etapas = [Etapa("import", OK, f"{len(arqs)} arquivos, rolo de {rolo.get('date')}")]

    # classificar (digiKam): basta haver alguma nota, pick ou etiqueta
    cor = _cor(eq.conv.get("print_label", "green"))
    nome_cor = NOME_COR.get(cor, cor.lower())
    verdes = [a for a in arqs if cor in (str(d[a].get("Label", "")).capitalize(),
                                         DIGIKAM_ID.get(str(d[a].get("ColorLabel", ""))))]
    aceitas = sum(p == "accepted" for p in picks.values())
    recusadas = sum(p == "rejected" for p in picks.values())
    classificado = any(picks[a] in ("accepted", "rejected") or int(d[a].get("Rating") or 0) > 0
                       or d[a].get("Label") or int(d[a].get("ColorLabel") or 0) for a in arqs)
    resumo = f"{aceitas} aceitas, {recusadas} recusadas, {len(arqs) - aceitas - recusadas} sem pick · {len(verdes)} {nome_cor}(s)"
    etapas.append(Etapa("classificar", OK if classificado else PENDENTE,
                        resumo if classificado else "nenhuma nota, pick ou etiqueta ainda",
                        "digiKam: nota, pick (recusadas ficam de fora), etiqueta verde"))

    # print (ramo lateral): verdes que ainda não foram para a gráfica
    h = hist.get("print") or {}
    enviadas = set(h.get("files") or [])
    saida_print = cfg.outbox / "print" / pasta.name
    if not enviadas and saida_print.is_dir():
        enviadas = {p.stem for p in saida_print.iterdir()}
    faltam = [a for a in verdes if a.stem not in enviadas]
    if not classificado:
        e = Etapa("print", PENDENTE, "depois de classificar")
    elif not verdes:
        e = Etapa("print", PULADO, f"nenhuma foto {nome_cor}")
    elif faltam:
        e = Etapa("print", PENDENTE, f"{len(faltam)} de {len(verdes)} {nome_cor}(s) ainda não enviada(s)")
    elif h:
        e = Etapa("print", OK, f"{len(verdes)} enviada(s) em {h['at']}")
    else:
        e = Etapa("print", OK, f"{len(verdes)} em {cfg.relativo(saida_print)} (envio não registrado)")
    e.lateral, e.comando = True, f"rolo print {rel}"
    etapas.append(e)

    # sheet: só faz sentido com JSON do Exif Notes
    en = [q for q in fi["frames"] if q.get("source") == "exifnotes"]
    jsons = sorted(cfg.inbox.glob("*.json")) if cfg.inbox.is_dir() else []
    if en:
        etapas.append(Etapa("sheet", OK, f"Exif Notes em {len(en)} quadros"))
    elif jsons:
        etapas.append(Etapa("sheet", PENDENTE, f"JSON em _inbox: {', '.join(j.name for j in jsons[:3])}",
                            f"rolo sheet {rel} --exifnotes _inbox/{jsons[0].name}"))
    else:
        etapas.append(Etapa("sheet", PULADO, "sem Exif Notes"))

    # skill roll-sheet: todo quadro com local (no roll.yaml ou GPS da própria câmera)
    sem_local = [n for n, a in enumerate(arqs, 1)
                 if quadros[n].get("lat") is None and not quadros[n].get("location") and not d[a].get("GPSLatitude")]
    etapas.append(Etapa("skill", PENDENTE if sem_local else OK,
                        f"{len(sem_local)} quadro(s) sem local {_faixas(sem_local)}" if sem_local
                        else "todos os quadros com local",
                        "Claude + skill roll-sheet: locais, lentes, horários"))

    # apply: o EXIF bate com o que o roll.yaml manda gravar?
    try:
        diferentes = [a for n, a in enumerate(arqs, 1)
                      if any(not _igual(v, d[a].get(t)) for t, v in _esperado(eq, rolo, n, quadros[n]).items())]
        if diferentes:
            nums = [n for n, a in enumerate(arqs, 1) if a in diferentes]
            e = Etapa("apply", PENDENTE, f"{len(diferentes)} arquivo(s) com EXIF diferente do roll.yaml {_faixas(nums)}")
        else:
            quando = f" (último apply: {hist['apply']['at']})" if hist.get("apply") else ""
            e = Etapa("apply", OK, "EXIF confere com o roll.yaml" + quando)
    except Erro as ex:
        e = Etapa("apply", PENDENTE, f"roll.yaml com erro: {ex}")
    e.comando = f"rolo apply {rel}"
    etapas.append(e)

    # álbuns: Immich + Google Photos, logo depois do apply (a IA não é obrigatória)
    modo = eq.conv.get("portfolio_pick")
    eleg = [a for a in arqs if (picks[a] == "accepted" if modo == "accepted" else picks[a] != "rejected")]
    etapas.append(etapa_albuns(hist, eleg, rel))

    # ai: não recusadas sem descrição
    validas = [(n, a) for n, a in enumerate(arqs, 1) if picks[a] != "rejected"]
    sem_desc = [n for n, a in validas
                if not (d[a].get("Description") or d[a].get("ImageDescription") or quadros[n].get("description"))]
    etapas.append(Etapa("ai", PENDENTE if sem_desc else OK,
                        f"{len(sem_desc)} sem descrição {_faixas(sem_desc)}" if sem_desc else "todas com descrição",
                        f"rolo ai {rel}"))

    # revisar (digiKam): ai:generated ainda presente
    com_ai = [n for n, a in validas if TAG_AI in _subject(d[a])]
    etapas.append(Etapa("revisar", PENDENTE if com_ai else OK,
                        f"{len(com_ai)} com {TAG_AI} {_faixas(com_ai)}" if com_ai else "nada a revisar",
                        f"digiKam: filtrar a tag {TAG_AI}, revisar e remover a tag"))
    return etapas


def etapa_albuns(hist, eleg, rel):
    """Etapa "álbuns" a partir do histórico `albums` (o `portfolio` antigo conta como já enviado)."""
    h, legado = hist.get("albums") or {}, hist.get("portfolio") or {}
    enviadas = set(h.get("files") or []) | set(legado.get("files") or [])
    quando = max(h.get("at", ""), legado.get("at", ""))
    faltam = [a for a in eleg if a.stem not in enviadas]
    if not quando:
        e = Etapa("álbuns", PENDENTE, "nunca enviado")
    elif faltam:
        e = Etapa("álbuns", PENDENTE, f"{len(faltam)} foto(s) nova(s) para enviar (último envio: {quando})")
    else:
        n_alb = len(h.get("albums") or {})
        detalhe = f"{len(enviadas & {a.stem for a in eleg})} foto(s) enviada(s)"
        detalhe += f" em {n_alb} álbum(ns)" if n_alb else ""
        detalhe += f", último envio {quando}"
        if (hist.get("apply") or {}).get("at", "") > quando:
            detalhe += " · ⚠ dados antigos no Immich/Google (apply depois do envio)"
        e = Etapa("álbuns", OK, detalhe)
    e.comando = f"rolo albums {rel}"
    return e


def atual(etapas):
    return next((e for e in etapas if e.estado == PENDENTE and not e.lateral), None)


def _mostrar_rolo(cfg, eq, pasta):
    etapas = avaliar(cfg, eq, pasta)
    rolo = F.ler(pasta)["roll"]
    agora = atual(etapas)
    equip = [eq.camera(rolo["camera"])["name"]]
    if rolo.get("film"):
        equip.append(eq.filme(rolo["film"])["name"])
    print(f"{cfg.relativo(pasta)}")
    print(f"{' · '.join(equip)} · {rolo.get('title')}\n")
    for e in etapas:
        if e.estado == OK:
            marca = "✓"
        elif e.estado == PULADO:
            marca = "–"
        elif e is agora or (e.lateral and e.detalhe != "depois de classificar"):
            marca = "●"
        else:
            marca = "○"
        print(f"  {marca} {e.nome:12} {e.detalhe}")
    lateral = [e for e in etapas if e.lateral and e.estado == PENDENTE and e.detalhe != "depois de classificar"]
    if agora:
        print(f"\nEtapa atual: {agora.nome}\n  {agora.comando}")
    else:
        print("\nRolo concluído.")
    for e in lateral:
        print(f"Também pendente: {e.nome}\n  {e.comando}")


def _pastas_de_rolo(cfg):
    return sorted(p.parent for p in cfg.root.rglob(F.NOME) if not ignorada(cfg, p))


def _panorama(cfg, eq, todos):
    if cfg.inbox.is_dir():
        entrada = [p for p in sorted(cfg.inbox.iterdir()) if p.is_dir() and imagens(p)]
        for p in entrada:
            print(f"_inbox/{p.name}  ({len(imagens(p))} arquivos)\n  ● import       rolo import\n")
    concluidos = 0
    for pasta in _pastas_de_rolo(cfg):
        try:
            etapas = avaliar(cfg, eq, pasta)
        except Erro as ex:
            print(f"{cfg.relativo(pasta)}\n  ! {ex}\n")
            continue
        agora = atual(etapas)
        lateral = [e for e in etapas if e.lateral and e.estado == PENDENTE and e.detalhe != "depois de classificar"]
        if not agora and not lateral:
            concluidos += 1
            if not todos:
                continue
        print(cfg.relativo(pasta))
        if agora:
            print(f"  ● {agora.nome:12} {agora.detalhe}")
        else:
            print("  ✓ concluído")
        for e in lateral:
            print(f"  ● {e.nome:12} {e.detalhe}")
        print()
    rolos = set(_pastas_de_rolo(cfg))
    antigas = {p.parent for p in cfg.root.rglob("*") if p.is_file() and p.suffix.lower() in (".jpg", ".tif", ".tiff", ".dng")
               and not ignorada(cfg, p)} - rolos
    if concluidos and not todos:
        print(f"{concluidos} rolo(s) concluído(s) (--all para ver).")
    if antigas:
        print(f"{len(antigas)} pasta(s) sem roll.yaml, fora do fluxo (`rolo adopt` traz para o fluxo; veja `rolo check`).")
    print("Detalhes de um rolo: rolo status PASTA")


def executar(cfg, eq, args):
    if args.folder:
        pasta = cfg.resolver(args.folder)
    elif (Path.cwd() / F.NOME).exists():
        pasta = Path.cwd()
    else:
        _panorama(cfg, eq, args.all)
        return
    if not F.caminho(pasta).exists():
        raise Erro(f"{cfg.relativo(pasta)} não tem roll.yaml (não passou pelo `rolo import`; "
                   f"se foi organizada à mão: `rolo adopt {cfg.relativo(pasta)}`).")
    _mostrar_rolo(cfg, eq, pasta)
