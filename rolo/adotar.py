"""rolo adopt: traz para o fluxo uma pasta organizada à mão, sem passar pelo `rolo import`.

Não renomeia nada. Monta o roll.yaml a partir do nome da pasta e do EXIF que já está nos arquivos (data, lente,
distância focal, GPS, cidade, evento), registra as fotos atuais como já enviadas (na chave `portfolio` do
.rolo-history.yaml, para o `rolo albums` não reenviá-las) e roda o `rolo apply`, que só padroniza sem apagar
o que existe e reindexa o PhotoPrism.
"""
from collections import Counter
from types import SimpleNamespace

from . import ficha as F
from .campos import ler_data
from .equip import _norm
from .manutencao import ignorada, ler_nome
from .metadados import aplicar
from .util import EXT_IMAGEM, Erro, exif_ler, imagens, trava

LER = ("DateTimeOriginal", "LensModel", "FocalLength", "Composite:GPSLatitude", "Composite:GPSLongitude",
       "City", "State", "Country", "ISO", "XMP-iptcExt:Event", "XMP-dc:Subject")


def lente_do_exif(eq, camera, texto):
    """Código da lente (de `camera`) cujo nome bate com o LensModel gravado; aceita a marca na frente
    ('Olympus Zuiko 50mm f1.4'). None se não achar."""
    if not texto:
        return None
    lentes = eq.lentes_da(camera)
    cod = eq.procurar("lenses", texto)
    if cod in lentes:
        return cod
    alvo = _norm(texto)
    return next((c for c, L in lentes.items() if L.get("model") and alvo.endswith(_norm(L["model"]))), None)


def montar(cfg, eq, pasta):
    """(ficha, avisos) para uma pasta sem roll.yaml. Erro se ela não puder entrar no fluxo."""
    rel = cfg.relativo(pasta)
    if F.caminho(pasta).exists():
        raise Erro(f"{rel} já tem roll.yaml")
    sidecars = sorted(p.name for p in pasta.iterdir() if p.suffix.lower() in (".xmp", ".acr"))
    if sidecars:
        raise Erro(f"{rel}: {len(sidecars)} sidecar(s) .xmp/.acr (ex.: {sidecars[0]}). Nota, pick e etiqueta "
                   "podem estar só neles, onde o rolo não lê: grave-os nos arquivos (digiKam) e apague os sidecars.")
    n = ler_nome(eq, pasta.name)
    if not n or not n["date"] or not n["camera"] or not (n["film"] or eq.digital(n["camera"])):
        raise Erro(f"{rel}: nome fora do padrão AAAAMMDD-CAMERA-filme-titulo ou com câmera/filme fora do "
                   "equipment.yaml (veja `rolo check`); renomeie pelo digiKam")
    arqs = imagens(pasta)
    if not arqs:
        raise Erro(f"{rel}: nenhuma imagem")
    camera, digital = n["camera"], eq.digital(n["camera"])
    exif = exif_ler(arqs, *LER, numerico=True)
    d = [exif.get(str(a), {}) for a in arqs]

    # no digital a câmera grava a lente; com lente fixa não há o que escolher
    sem_lente = digital or eq.camera(camera).get("fixed_lens")
    lentes = [None if sem_lente else lente_do_exif(eq, camera, x.get("LensModel")) for x in d]
    lente_rolo = (Counter(L for L in lentes if L).most_common(1) or [(None,)])[0][0]
    avisos = []
    if not sem_lente:
        estranhas = sorted({str(x["LensModel"]) for x, L in zip(d, lentes) if x.get("LensModel") and not L})
        if estranhas:
            avisos.append(f"lente(s) fora do equipment.yaml: {', '.join(estranhas)} "
                          f"(o `rolo apply` gravaria {lente_rolo or 'nenhuma'} nesses quadros)")
    if lente_rolo:
        vazios = [i for i, (x, L) in enumerate(zip(d, lentes), 1) if not x.get("LensModel")]
        if vazios:
            avisos.append(f"arquivo(s) {', '.join(map(str, vazios))} sem lente no EXIF: o `rolo apply` grava "
                          f"{lente_rolo} (corrija `lens` no roll.yaml se não for)")
    isos = Counter(int(x["ISO"]) for x in d if isinstance(x.get("ISO"), (int, float)))

    rolo = {"folder": str(rel), "camera": camera, "film": n["film"], "lens": lente_rolo,
            "date": n["date"].isoformat(), "title": n["title"], "count": len(arqs), "offset": 0}
    if not digital:
        rolo["iso"] = isos.most_common(1)[0][0] if isos else eq.filme(n["film"])["iso"]
    frames = []
    for i, (x, lente) in enumerate(zip(d, lentes), 1):
        q = {"n": i, "source": "adopt"}
        if lente and lente != lente_rolo:
            q["lens"] = lente
        # zoom: sem isso o apply gravaria a focal padrão da lente por cima da que já está no arquivo
        focal = x.get("FocalLength")
        if lente and isinstance(focal, (int, float)) and focal and round(focal) != eq.lente(lente).get("focal_length"):
            q["focal_length"] = round(focal)
        if not digital and x.get("DateTimeOriginal"):  # no digital o apply não grava a data
            try:
                q["date"] = ler_data(x["DateTimeOriginal"]).strftime("%Y-%m-%d %H:%M:%S")
            except Erro:
                avisos.append(f"arquivo {i}: DateTimeOriginal ilegível '{x['DateTimeOriginal']}'")
        if isinstance(x.get("GPSLatitude"), (int, float)) and isinstance(x.get("GPSLongitude"), (int, float)):
            q["lat"], q["lon"] = round(x["GPSLatitude"], 7), round(x["GPSLongitude"], 7)
        for campo, tag in (("city", "City"), ("state", "State"), ("country", "Country"), ("album", "Event")):
            if str(x.get(tag) or "").strip():
                q[campo] = str(x[tag]).strip()
        assunto = x.get("Subject") or []
        if "personal" in (assunto if isinstance(assunto, list) else [assunto]):
            q["personal"] = True
        if len(q) > 2:
            frames.append(q)
    return {"roll": rolo, "frames": frames}, avisos


def adotar(cfg, eq, pasta, enviadas=True, simular=False, padronizar=True):
    fi, avisos = montar(cfg, eq, pasta)
    rolo, frames = fi["roll"], fi["frames"]
    if not simular:
        with trava(pasta):
            F.gravar(pasta, fi)
            if enviadas:
                F.registrar(pasta, "portfolio", imagens(pasta), unir=True)
    datas = sum("date" in q for q in frames)
    gps = sum("lat" in q for q in frames)
    print(f"{cfg.relativo(pasta)}\n  {rolo['count']} arquivos · {rolo['camera']}"
          + (f" · {rolo['film']} ISO {rolo['iso']}" if rolo.get("film") else "")
          + (f" · lente {rolo['lens']}" if rolo.get("lens") else "")
          + (f" · {datas} com data" if rolo.get("film") else "") + f" · {gps} com GPS"
          + (" · marcadas como já enviadas" if enviadas else ""))
    for a in avisos:
        print(f"  [aviso] {a}")
    if padronizar and not simular:
        aplicar(cfg, eq, SimpleNamespace(folder=str(pasta), dry_run=False, show=0))
        print()


def _candidatas(cfg, alvo):
    return sorted({p.parent for p in alvo.rglob("*") if p.is_file() and p.suffix.lower() in EXT_IMAGEM
                   and not ignorada(cfg, p)} - {p.parent for p in alvo.rglob(F.NOME)})


def executar(cfg, eq, args):
    alvo = cfg.resolver(args.folder)
    if not alvo.is_dir():
        raise Erro(f"Pasta não encontrada: {args.folder}")
    enviadas, simular, padronizar = not args.unsent, args.dry_run, not args.no_apply
    if simular:
        print("(simulação: nada é gravado)\n")
    if imagens(alvo):
        adotar(cfg, eq, alvo, enviadas, simular, padronizar)
        rel = cfg.relativo(alvo)
        print(f"Próximo: rolo status {rel}" + ("" if padronizar else f" → rolo apply {rel}") + f" → rolo ai {rel}")
        return
    pastas = _candidatas(cfg, alvo)
    if not pastas:
        raise Erro(f"Nenhuma pasta sem roll.yaml em {cfg.relativo(alvo)}")
    adotadas, puladas = 0, []
    for p in pastas:
        try:
            adotar(cfg, eq, p, enviadas, simular, padronizar)
            adotadas += 1
        except Erro as e:
            puladas.append(str(e))
    if puladas:
        print(f"\nPuladas ({len(puladas)}):")
        for m in puladas:
            print(f"  - {m}")
    print(f"\n{adotadas} pasta(s) {'adotável(is)' if simular else 'adotada(s)'}, {len(puladas)} pulada(s).")
    if adotadas and not simular:
        print("Próximo: rolo status" + ("" if padronizar else " → rolo apply PASTA") + " → rolo ai PASTA")
