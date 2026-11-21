"""Junta base + roll.yaml + Exif Notes de cada quadro e traduz para argumentos do exiftool."""
import datetime as dt
import random

from .util import Erro

# Campos aceitos em ranges e frames do roll.yaml
FIELDS = ["lens", "focal_length", "aperture", "shutter", "flash", "light", "date",
          "lat", "lon", "location", "sublocation", "city", "state", "country",
          "title", "description", "people", "keywords", "filters", "exposures", "album", "personal"]

LIGHT = {"daylight": "Daylight", "cloudy": "Cloudy", "shade": "Shade", "tungsten": "Tungsten",
         "fluorescent": "Fluorescent", "flash": "Flash", "unknown": "Unknown"}

TAG_AI = "ai:generated"


def faixa_numeros(spec):
    """'1-10,12,15-16' -> [1..10, 12, 15, 16]"""
    nums = []
    for parte in str(spec).replace(" ", "").split(","):
        if not parte:
            continue
        if "-" in parte:
            a, b = parte.split("-", 1)
            nums.extend(range(int(a), int(b) + 1))
        else:
            nums.append(int(parte))
    return nums


def quadro_do_arquivo(rolo, n):
    """Número do quadro no filme para o arquivo n (e vice-versa). Com files_reversed, o último arquivo é o quadro 1."""
    return int(rolo["count"]) + 1 - n if rolo.get("files_reversed") else n


def ler_data(texto):
    texto = str(texto).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y:%m:%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(texto, fmt)
        except ValueError:
            pass
    raise Erro(f"Data inválida: '{texto}' (use AAAA-MM-DD HH:MM)")


def horarios_faixa(faixa, nums):
    """Distribui horários crescentes entre start e end, com passos levemente variados."""
    if "start" not in faixa:
        return {}
    ini = ler_data(faixa["start"])
    fim = ler_data(faixa["end"]) if faixa.get("end") else ini + dt.timedelta(minutes=5 * len(nums))
    if len(nums) == 1:
        return {nums[0]: ini}
    rnd = random.Random(nums[0])
    pesos = [rnd.uniform(0.6, 1.4) for _ in nums[1:]]
    total = (fim - ini).total_seconds() * 0.97
    t, saida = ini, {nums[0]: ini}
    for n, p in zip(nums[1:], pesos):
        t += dt.timedelta(seconds=round(total * p / sum(pesos)))
        saida[n] = t
    return saida


def montar_quadros(ficha, total):
    """Retorna {n: {campo: valor, '_source': {campo: origem}}} para n = 1..total."""
    quadros = {n: {"_source": {}} for n in range(1, total + 1)}

    def aplicar(n, dados, origem):
        if n not in quadros:
            return
        q = quadros[n]
        for c in FIELDS:
            if dados.get(c) not in (None, "", []):
                if q["_source"].get(c) == "exifnotes" and origem != "exifnotes":
                    continue
                q[c] = dados[c]
                q["_source"][c] = origem

    for faixa in ficha.get("ranges", []):
        nums = faixa_numeros(faixa.get("frames", ""))
        # arquivos invertidos: o horário cresce do maior arquivo para o menor (ordem do filme)
        horas = horarios_faixa(faixa, sorted(nums, reverse=bool(ficha.get("roll", {}).get("files_reversed"))))
        for n in nums:
            dados = dict(faixa)
            if n in horas:
                dados["date"] = horas[n].strftime("%Y-%m-%d %H:%M:%S")
            aplicar(n, dados, faixa.get("source", "manual"))
    # frames manuais primeiro, Exif Notes por último (prioridade máxima)
    for q in sorted(ficha.get("frames", []), key=lambda q: q.get("source") == "exifnotes"):
        aplicar(int(q["n"]), q, q.get("source", "manual"))
    return quadros


def _lista(tag, valores):
    args = []
    for v in valores:
        args += [f"-{tag}-={v}", f"-{tag}+={v}"]
    return args


def args_base(eq, rolo):
    """Tags iguais para o rolo inteiro."""
    conv = eq.conv
    ano = str(rolo["date"])[:4]
    args = [f"-Artist={conv.get('artist', '')}", f"-XMP-dc:Creator={conv.get('artist', '')}"]
    if conv.get("copyright"):
        c = conv["copyright"].replace("{year}", ano)
        args += [f"-Copyright={c}", f"-XMP-dc:Rights={c}"]
    if eq.digital(rolo["camera"]):
        return args
    cam = eq.camera(rolo["camera"])
    filme = eq.filme(rolo["film"])
    make = filme["name"] if conv.get("make") == "film" else cam["make"]
    args += [f"-Make={make}", f"-Model={cam['model']}", f"-ISO={rolo.get('iso') or filme['iso']}"]
    if cam.get("serial"):
        args.append(f"-SerialNumber={cam['serial']}")
    args += _lista("XMP-dc:Subject", [f"film:{filme['name']}", f"camera:{cam['name']}"])
    return args


def _lente(eq, rolo, n, q):
    """Lente do quadro (dict de equipment.yaml) ou None. Confere se a lente é da câmera do rolo.
    No digital, só a `lens` do quadro/faixa (a do rolo não sobrescreve a lente que a câmera gravou)."""
    cod = q.get("lens") if eq.digital(rolo["camera"]) else (q.get("lens") or rolo.get("lens"))
    if not cod or eq.camera(rolo["camera"]).get("fixed_lens"):
        return None
    L = eq.lente(cod)
    if rolo["camera"] not in L.get("cameras", []):
        raise Erro(f"Quadro {n}: lente {cod} não é da câmera {rolo['camera']} "
                   f"(acrescente {rolo['camera']} em lenses.{cod}.cameras no equipment.yaml, se ela usa adaptador)")
    return L


def args_lente(L, q):
    args = [f"-LensMake={L['make']}", f"-LensModel={L['model']}",
            f"-Lens={L['make']} {L['model']}", f"-MaxApertureValue={L['max_aperture']}",
            f"-FocalLength={q.get('focal_length') or L['focal_length']}"]
    if L.get("serial"):
        args.append(f"-LensSerialNumber={L['serial']}")
    return args


def album_de(eq, rolo, n_arquivo, q):
    """Nome completo do álbum de uma foto: '<Prefixo> - <sessão>'.
    Prefixo: filme → Analog; digital com lente vintage → Vintage; outro digital → Photography;
    digital com personal: true → sem prefixo. Sessão: `album` da faixa/quadro, senão '<ano> <título do rolo>'."""
    sessao = str(q.get("album") or "").strip()
    if not sessao:
        titulo = rolo.get("title") or rolo.get("folder") or ""
        sessao = f"{str(rolo['date'])[:4]} {titulo}".strip()
    if not eq.digital(rolo["camera"]):
        prefixo = "Analog"
    elif q.get("personal"):
        prefixo = None
    else:
        L = _lente(eq, rolo, n_arquivo, q)
        prefixo = "Vintage" if L and L.get("vintage") else "Photography"
    nome = f"{prefixo} - {sessao}" if prefixo else sessao
    return nome.replace("/", "-")


def args_quadro(eq, rolo, n, q):
    """Tags de um quadro (já mesclado)."""
    digital = eq.digital(rolo["camera"])
    args = [f"-ImageNumber={n}"]
    fuso = eq.conv.get("timezone", "")
    L = _lente(eq, rolo, n, q)
    if L:
        # no digital, só com lente explícita (vintage adaptada): a câmera não grava a lente
        args += args_lente(L, q)
    if not digital:
        if q.get("aperture"):
            args += [f"-FNumber={q['aperture']}", f"-ApertureValue={q['aperture']}"]
        if q.get("shutter"):
            args += [f"-ExposureTime={q['shutter']}", f"-ShutterSpeedValue={q['shutter']}"]
        if "flash" in q:
            args.append(f"-Flash={'Fired' if q['flash'] else 'No Flash'}")
        if q.get("light"):
            args.append(f"-LightSource={LIGHT.get(str(q['light']).lower(), q['light'])}")
        # data: a do quadro, ou a do rolo ao meio-dia + n segundos (mantém a ordem do rolo)
        if q.get("date"):
            d = ler_data(q["date"])
        else:
            d = ler_data(rolo["date"]).replace(hour=12) + dt.timedelta(seconds=n)
        ds = d.strftime("%Y:%m:%d %H:%M:%S")
        args += [f"-DateTimeOriginal={ds}", f"-CreateDate={ds}"]
        if fuso:
            args += [f"-OffsetTimeOriginal={fuso}", f"-OffsetTime={fuso}"]
    if q.get("lat") is not None and q.get("lon") is not None:
        lat, lon = float(q["lat"]), float(q["lon"])
        args += [f"-GPSLatitude={abs(lat)}", f"-GPSLatitudeRef={'S' if lat < 0 else 'N'}",
                 f"-GPSLongitude={abs(lon)}", f"-GPSLongitudeRef={'W' if lon < 0 else 'E'}"]
    local = ", ".join(x for x in (q.get("location"), q.get("sublocation")) if x)
    if local:
        args.append(f"-XMP-iptcCore:Location={local}")
    for campo, tag in (("city", "City"), ("state", "State"), ("country", "Country")):
        if q.get(campo):
            args.append(f"-{tag}={q[campo]}")
    if q.get("title"):
        args += [f"-XMP-dc:Title={q['title']}", f"-IPTC:ObjectName={q['title'][:64]}"]
    if q.get("description"):
        d = q["description"]
        args += [f"-XMP-dc:Description={d}", f"-ImageDescription={d}", f"-UserComment={d}",
                 f"-IPTC:Caption-Abstract={d[:2000]}"]
    if q.get("people"):
        args += _lista("XMP-iptcExt:PersonInImage", q["people"])
    # sem album/personal, limpa o que um apply anterior gravou
    args.append(f"-XMP-iptcExt:Event={q.get('album') or ''}")
    kws = list(q.get("keywords", []))
    if q.get("personal"):
        kws.append("personal")
    kws += [f"filter:{f}" for f in q.get("filters", [])]
    if int(q.get("exposures", 1) or 1) > 1:
        kws.append("multiple-exposure")
    args += _lista("XMP-dc:Subject", kws)
    if not q.get("personal"):
        args.append("-XMP-dc:Subject-=personal")
    return args
