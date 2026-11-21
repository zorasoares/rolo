"""roll.yaml: a ficha do rolo, quadro a quadro. Também lê o JSON do Exif Notes."""
import datetime as dt
import json
import re
from pathlib import Path

from .campos import FIELDS, ler_data, quadro_do_arquivo
from .util import Erro, escolher, interativo
from .yamlio import carregar, despejar

NOME = "roll.yaml"
HISTORICO = ".rolo-history.yaml"  # quando apply/print/albums terminaram (lido pelo `rolo status`)

CABECALHO = """\
# Roll sheet — read by `rolo apply`.
# Priority: Exif Notes frames > manual/skill frames > ranges > roll.
# Lenses always by their code in equipment.yaml.
# Frame numbers below are FILE numbers (_01, _02…).
# source: adopt = copied from the EXIF the files already had (`rolo adopt`, folder organised by hand).
# roll.scan_order: how the lab delivered the scans (reversed = last scan was frame 1;
#   `rolo import` already renamed them in film order).
# roll.files_reversed: true = files were NOT renamed, so file _01 is the LAST frame of the film.
#   Exif Notes frames are mapped and range times run from the highest file to the lowest.
# roll.share: false = commissioned roll: `rolo albums` only exports to _outbox/albuns/, no upload.
#
# Fields accepted in ranges and frames:
#   lens, focal_length, aperture ("8"), shutter ("1/125"), flash (true/false), light,
#   date ("2026-11-15 14:30"), lat, lon (decimal degrees, negative = S/W),
#   location, sublocation, city, state, country, title, description, people, keywords,
#   filters, exposures,
#   album (session, e.g. "2026 Halloween"; album = "Analog - 2026 Halloween"; default "<year> <roll title>"),
#   personal (true = family photo: keyword personal; digital album without the Analog/Vintage/Photography prefix)
# A range may have start/end ("2026-11-15 14:00") to spread capture times.
#
# Range example:
#   - frames: 1-10
#     source: skill
#     location: MASP
#     lat: -23.561414
#     lon: -46.655881
#     city: São Paulo
#     state: SP
#     country: Brazil
#     start: 2026-11-15 14:00
#     end: 2026-11-15 15:10
#     album: 2026 Halloween

"""

ORDEM_ROLO = ["folder", "camera", "film", "lens", "date", "iso", "title", "count", "offset",
              "scan_order", "files_reversed", "share"]
ORDEM_ITEM = ["n", "frames", "source"] + FIELDS + ["start", "end"]


def caminho(pasta):
    return Path(pasta) / NOME


def ler(pasta):
    p = caminho(pasta)
    if not p.exists():
        raise Erro(f"{p} não existe. A pasta foi importada com `rolo import`?")
    d = carregar(p)
    if "roll" not in d:
        raise Erro(f"{p} sem a seção roll:")
    d["ranges"] = d.get("ranges") or []
    d["frames"] = d.get("frames") or []
    return d


def _ordenado(d, ordem):
    chaves = [k for k in ordem if k in d] + [k for k in d if k not in ordem]
    return {k: d[k] for k in chaves if d[k] not in (None, "", [])}


def gravar(pasta, ficha):
    dados = {"roll": _ordenado(ficha["roll"], ORDEM_ROLO),
             "ranges": [_ordenado(f, ORDEM_ITEM) for f in ficha.get("ranges", [])],
             "frames": [_ordenado(q, ORDEM_ITEM) for q in sorted(ficha.get("frames", []), key=lambda q: q["n"])]}
    caminho(pasta).write_text(CABECALHO + despejar(dados), encoding="utf-8")


def historico(pasta):
    p = Path(pasta) / HISTORICO
    return carregar(p) if p.exists() else {}


def registrar(pasta, etapa, arquivos=None, unir=False, albuns=None):
    """Anota no .rolo-history.yaml que `etapa` terminou agora (e com quais arquivos, se for envio).
    unir: soma os arquivos (e álbuns) aos já registrados, em vez de substituir.
    albuns: {nome do álbum: [arquivos]} enviados nesta execução."""
    h = historico(pasta)
    antes = (h.get(etapa) or {}) if unir else {}
    h[etapa] = {"at": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    if arquivos is not None or antes.get("files"):
        novos = {Path(a).stem for a in arquivos or []}
        h[etapa]["files"] = sorted(novos | set(antes.get("files") or []))
    if albuns is not None or antes.get("albums"):
        todos = {k: set(v or []) for k, v in (antes.get("albums") or {}).items()}
        for nome, arqs in (albuns or {}).items():
            todos.setdefault(nome, set()).update(Path(a).stem for a in arqs)
        h[etapa]["albums"] = {k: sorted(v) for k, v in sorted(todos.items())}
    (Path(pasta) / HISTORICO).write_text(despejar(h), encoding="utf-8")


# ---------------------------------------------------------------- Exif Notes

def ler_exifnotes(arquivo):
    try:
        with open(arquivo, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise Erro(f"Não consegui ler o JSON do Exif Notes {arquivo}: {e}")


def sugestoes_rolo(eq, en):
    """Sugestões para o menu do import, a partir do JSON (nunca gravadas direto)."""
    cam = en.get("camera") or {}
    filme = en.get("filmStock") or {}
    nome_filme = " ".join(x for x in (filme.get("make"), filme.get("model")) if x)
    return {
        "camera": eq.procurar("cameras", cam.get("model"))
                  or eq.procurar("cameras", f"{cam.get('make', '')} {cam.get('model', '')}"),
        "film": eq.procurar("films", filme.get("model")) or eq.procurar("films", nome_filme),
        "iso": en.get("iso"),
        "title": en.get("name"),
        "date": (en.get("date") or "")[:10] or None,
        "camera_text": cam.get("model"),
        "film_text": nome_filme,
    }


def endereco(formatado):
    """'Av. Paulista, 1578 - Bela Vista, São Paulo - SP, 01310-200, Brazil' -> campos IPTC."""
    if not formatado:
        return {}
    partes = [p.strip() for p in formatado.split(",") if p.strip()]
    partes = [p for p in partes if not re.fullmatch(r"\d{5}-?\d{3}", p)]  # CEP
    saida = {}
    if len(partes) >= 2:
        saida["country"] = partes.pop()
    for i, p in enumerate(partes):
        m = re.fullmatch(r"(.+?) - ([A-Z]{2})", p)
        if m:
            saida["city"], saida["state"] = m[1], m[2]
            antes = partes[:i]
            break
    else:
        antes = partes[:-1] if len(partes) > 1 else partes
        if len(partes) > 1:
            saida["city"] = partes[-1]
    if antes:
        local, resto = antes[0], antes[1:]
        if resto:
            m = re.fullmatch(r"(\S+) - (.+)", resto[0])
            if m:
                local, saida["sublocation"] = f"{local}, {m[1]}", m[2]
            else:
                saida["sublocation"] = resto[0]
        saida["location"] = local
    return saida


def politica_datas(rolo_data, frames, politica):
    """Decide o que fazer com datas de quadros muito distantes da data do rolo."""
    base = ler_data(rolo_data).date()
    distantes = [f for f in frames if f.get("date") and abs((ler_data(f["date"]).date() - base).days) > 1]
    if not distantes or politica:
        return politica or "keep"
    print(f"\n[atenção] {len(distantes)} quadro(s) do Exif Notes têm data a mais de 1 dia do rolo ({base}):")
    for f in distantes[:6]:
        print(f"   quadro {f.get('count')}: {f['date']}")
    print("   Parece ser a hora da anotação, não a do clique.")
    if not interativo():
        print("   Sem terminal: usando a data do rolo e descartando o horário (--dates ignore).")
        return "ignore"
    return escolher("O que fazer com essas datas?", [
        ("ignore", "usar a data do rolo e descartar o horário"),
        ("roll-time", "usar a data do rolo mantendo o horário anotado"),
        ("keep", "manter a data do Exif Notes"),
    ], padrao="ignore")


def quadros_exifnotes(eq, en, rolo, politica=None):
    """Converte os frames do JSON em frames do roll.yaml (source = exifnotes)."""
    frames = en.get("frames", [])
    politica = politica_datas(rolo["date"], frames, politica)
    base = ler_data(rolo["date"]).date()
    desloc = int(rolo.get("offset", 0) or 0)
    lentes_camera = eq.lentes_da(rolo["camera"])
    quadros = []
    for f in frames:
        q = {"n": quadro_do_arquivo(rolo, int(f["count"]) + desloc), "source": "exifnotes"}
        if f.get("shutter"):
            q["shutter"] = str(f["shutter"]).replace('"', "")
        if f.get("aperture"):
            q["aperture"] = str(f["aperture"])
        if f.get("focalLength"):
            q["focal_length"] = int(f["focalLength"])
        if "flashUsed" in f:
            q["flash"] = bool(f["flashUsed"])
        if f.get("lightSource"):
            q["light"] = f["lightSource"]
        if f.get("note"):
            q["description"] = f["note"].strip()
        loc = f.get("location") or {}
        if loc.get("latitude") is not None:
            q["lat"], q["lon"] = loc["latitude"], loc["longitude"]
        q.update(endereco(f.get("formattedAddress")))
        if (f.get("noOfExposures") or 1) > 1:
            q["exposures"] = int(f["noOfExposures"])
        filtros = [" ".join(x.capitalize() if x.islower() else x for x in
                            f"{fl.get('make', '')} {fl.get('model', '')}".split())
                   for fl in f.get("filters") or []]
        if filtros:
            q["filters"] = filtros
        lente = (f.get("lens") or {}).get("model")
        if lente and lentes_camera:
            cod = eq.resolver_alias("lenses", lente, lentes_camera, "Lente")
            if cod:
                q["lens"] = cod
        if f.get("date"):
            d = ler_data(f["date"])
            longe = abs((d.date() - base).days) > 1
            if longe and politica == "ignore":
                pass
            elif longe and politica == "roll-time":
                q["date"] = dt.datetime.combine(base, d.time()).strftime("%Y-%m-%d %H:%M")
            else:
                q["date"] = d.strftime("%Y-%m-%d %H:%M")
        quadros.append(q)
    return quadros
