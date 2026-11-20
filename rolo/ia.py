"""rolo ai: título, descrição e keywords por IA local (Ollama), só onde falta descrição.

Nunca altera pixels. Toda foto descrita recebe a keyword `ai:generated` para revisão no digiKam.
As keywords vêm só do vocabulário de tags.yaml, gravadas como grupo:termo (light:blue-hour); o que a IA quis marcar fora dele vai para tags-suggested.txt.
"""
import base64
import json
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from . import ficha as F
from .campos import TAG_AI, _lista, montar_quadros
from .util import TAGS_PICK, Erro, pick, exif_gravar, exif_ler, imagens, para_jpg, trava
from .yamlio import carregar

# campos de keyword que o digiKam espelha; os quatro andam juntos
CAMPOS_KW = ("XMP-dc:Subject", "XMP-digiKam:TagsList", "XMP-lr:HierarchicalSubject", "IPTC:Keywords")
MAX_KW = 8

PROMPT = """Você cataloga fotografias de um acervo pessoal ({tipo}).
Descreva APENAS o que é visível na imagem, em português do Brasil.

Contexto conhecido (use só na descrição, para nomear o lugar; não invente além disso):
{contexto}

Vocabulário de keywords (escolha só daqui, copiando exatamente como está, com o prefixo):
{vocabulario}

Regras:
- title: curto (até 8 palavras), sem ponto final.
- description: 1 a 2 frases objetivas sobre a cena. Detalhes como roupas, acessórios e objetos ficam aqui.
- keywords: 0 a {max_kw}, só do vocabulário. Um objeto só vira keyword se for o tema da foto. Lista vazia é aceitável.
- Nunca use lugar, cidade, bairro, país, evento, data ou nomes como keyword: isso já está em outros campos.
- other: até 3 termos fora do vocabulário que seriam realmente úteis para buscar esta foto, em inglês, minúsculas, com hífen no lugar de espaço e sem prefixo (pode ficar vazio).
- Nunca invente nomes de pessoas, marcas ou lugares que não estejam no contexto ou legíveis na foto.
- Não comente sobre qualidade técnica, edição ou estilo fotográfico.
Responda só com o JSON."""

GRUPOS = {"genre": "gênero", "technique": "técnica", "subject": "assunto", "light": "hora e luz",
          "framing": "plano", "film_defects": "defeitos de filme (só se evidente)"}


def _norm(k):
    return str(k).strip().lower()


def _vocabulario(cfg):
    """{grupo: [tags]} de tags.yaml, normalizado."""
    arq = Path(cfg["ROLO_TAGS"])
    if not arq.exists():
        raise Erro(f"Vocabulário de tags não encontrado: {arq}. Crie o arquivo (veja o README) ou ajuste ROLO_TAGS.")
    vocab = {g: [_norm(t) for t in (tags or []) if _norm(t)] for g, tags in carregar(arq).items()}
    if not any(vocab.values()):
        raise Erro(f"{arq} não tem nenhuma tag.")
    return vocab


def _plano(vocab):
    """Tags como são gravadas: grupo:termo."""
    return sorted({f"{g}:{t}" for g, tags in vocab.items() for t in tags})


def _esquema(vocab):
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "keywords": {"type": "array", "items": {"type": "string", "enum": _plano(vocab)}, "maxItems": MAX_KW},
            "other": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        },
        "required": ["title", "description", "keywords", "other"],
    }


def _separar(resp, permitidas):
    """(keywords aceitas, sugestões fora do vocabulário) da resposta do modelo."""
    kws, fora = [], []
    for k in resp.get("keywords", []):
        k = _norm(k)
        if k and k not in kws:
            (kws if k in permitidas else fora).append(k)
    fora += [_norm(k) for k in resp.get("other", []) if _norm(k)]
    return kws[:MAX_KW], list(dict.fromkeys(fora))


def _keywords_ia_antigas(atuais, grupos, protegidas):
    """Keywords de uma foto que vieram da IA e devem sair no --redo: ai:generated e as com prefixo de um
    grupo do vocabulário. Fotos da versão antiga (sem nenhuma tag de grupo) perdem também as tags simples,
    menos as do roll.yaml; camera:, film:, filter: e hierárquicas do digiKam (People/...) sempre ficam."""
    def do_grupo(k):
        return k.partition(":")[0] in grupos and ":" in k
    antiga = not any(do_grupo(k) for k in atuais)
    return [k for k in atuais if k == TAG_AI or do_grupo(k)
            or (antiga and ":" not in k and "/" not in k and k not in protegidas)]


def _contexto(eq, rolo, q):
    linhas = []
    for campo, rotulo in (("location", "Local"), ("sublocation", "Bairro"), ("city", "Cidade"),
                          ("state", "Estado"), ("country", "País")):
        if q.get(campo):
            linhas.append(f"- {rotulo}: {q[campo]}")
    if q.get("people"):
        linhas.append(f"- Pessoas: {', '.join(q['people'])}")
    if q.get("date"):
        linhas.append(f"- Data/hora: {q['date']}")
    linhas.append(f"- Rolo: {rolo.get('title')}")
    if q.get("flash"):
        linhas.append("- Foto feita com flash")
    return "\n".join(linhas)


def _tipo(eq, rolo):
    if eq.digital(rolo["camera"]):
        return "câmera digital"
    filme = eq.filme(rolo["film"])
    return f"filme {'preto e branco' if filme.get('type') == 'bw' else 'colorido'} {filme['name']}"


def _ollama(cfg, imagem_b64, prompt, esquema):
    corpo = {"model": cfg["ROLO_AI_MODEL"], "stream": False, "format": esquema,
             "options": {"temperature": 0.2},
             "messages": [{"role": "user", "content": prompt, "images": [imagem_b64]}]}
    req = urllib.request.Request(cfg["OLLAMA_HOST"].rstrip("/") + "/api/chat",
                                 data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise Erro(f"Ollama respondeu {e.code}: {e.read().decode()[:300]}")
    except urllib.error.URLError as e:
        raise Erro(f"Não consegui falar com o Ollama em {cfg['OLLAMA_HOST']}: {e.reason}")
    try:
        return json.loads(resp["message"]["content"])
    except (KeyError, json.JSONDecodeError):
        raise Erro(f"Resposta inesperada do modelo: {str(resp)[:300]}")


def verificar_ollama(cfg):
    try:
        with urllib.request.urlopen(cfg["OLLAMA_HOST"].rstrip("/") + "/api/tags", timeout=10) as r:
            modelos = [m["name"] for m in json.loads(r.read()).get("models", [])]
    except (urllib.error.URLError, OSError) as e:
        raise Erro(f"Ollama não está acessível em {cfg['OLLAMA_HOST']} ({e}). "
                   "No PC: `systemctl status ollama`; em outra máquina, ajuste OLLAMA_HOST.")
    modelo = cfg["ROLO_AI_MODEL"]
    if modelo not in modelos and f"{modelo}:latest" not in modelos:
        raise Erro(f"Modelo {modelo} não está no Ollama. Rode: ollama pull {modelo}")


def _lista_exif(d, campo):
    v = d.get(campo) or []
    return [str(x) for x in v] if isinstance(v, list) else [str(v)]


def _registrar_sugestoes(cfg, sugestoes):
    """Anexa (tag, pasta, arquivo) em tags-suggested.txt, ao lado do tags.yaml."""
    if not sugestoes:
        return
    arq = Path(cfg["ROLO_TAGS"]).with_name("tags-suggested.txt")
    with open(arq, "a", encoding="utf-8") as f:
        for tag, a in sugestoes:
            f.write(f"{tag}\t{cfg.relativo(a.parent)}\t{a.name}\n")
    mais = ", ".join(f"{t} ({c})" for t, c in Counter(t for t, _ in sugestoes).most_common(5))
    print(f"Sugestões fora do vocabulário em {arq.name}: {mais}")


def executar(cfg, eq, args):
    pasta = cfg.resolver(args.folder)
    fi = F.ler(pasta)
    rolo = fi["roll"]
    arquivos = imagens(pasta)
    quadros = montar_quadros(fi, len(arquivos))
    vocab = _vocabulario(cfg)
    if eq.digital(rolo["camera"]):
        vocab.pop("film_defects", None)
    atuais = exif_ler(arquivos, "XMP-dc:Description", "ImageDescription", *CAMPOS_KW, *TAGS_PICK)

    alvo, recusadas = [], 0
    for n, a in enumerate(arquivos, 1):
        d = atuais.get(str(a), {})
        if pick(d) == "rejected":
            recusadas += 1
            continue
        desc = d.get("Description") or d.get("ImageDescription")
        if args.redo and TAG_AI in _lista_exif(d, "Subject"):
            alvo.append((n, a))
        elif not desc and not quadros[n].get("description"):
            alvo.append((n, a))
    if recusadas:
        print(f"{recusadas} foto(s) recusada(s) no digiKam ignorada(s).")
    if args.limit:
        alvo = alvo[: args.limit]
    if not alvo:
        print("Nada a fazer: todos os quadros já têm descrição.")
        return
    verificar_ollama(cfg)
    print(f"IA ({cfg['ROLO_AI_MODEL']} em {cfg['OLLAMA_HOST']}): {len(alvo)} quadro(s)")
    tipo = _tipo(eq, rolo)
    esquema, permitidas = _esquema(vocab), set(_plano(vocab))
    grupos = set(_vocabulario(cfg))  # inclui film_defects: o --redo limpa mesmo se o rolo for digital
    vocabulario = "\n".join(f"- {GRUPOS.get(g, g)}: {', '.join(f'{g}:{x}' for x in t)}" for g, t in vocab.items() if t)
    lotes, sugestoes = [], []
    with trava(pasta), tempfile.TemporaryDirectory() as tmp:
        for i, (n, a) in enumerate(alvo, 1):
            t0 = time.time()
            mini = Path(tmp) / f"{n}.jpg"
            para_jpg(a, mini, lado_maior=1024, qualidade=85)
            prompt = PROMPT.format(tipo=tipo, contexto=_contexto(eq, rolo, quadros[n]),
                                   vocabulario=vocabulario, max_kw=MAX_KW)
            r = _ollama(cfg, base64.b64encode(mini.read_bytes()).decode(), prompt, esquema)
            kws, fora = _separar(r, permitidas)
            sugestoes += [(k, a) for k in fora]
            titulo, desc = r.get("title", "").strip(), r.get("description", "").strip()
            print(f"  [{i}/{len(alvo)}] {a.name} ({time.time() - t0:.0f}s): {titulo} [{', '.join(kws) or '-'}]")
            # título da ficha (roll.yaml) tem prioridade sobre o da IA
            ar = [] if quadros[n].get("title") else [f"-XMP-dc:Title={titulo}", f"-IPTC:ObjectName={titulo[:64]}"]
            ar += [f"-XMP-dc:Description={desc}", f"-ImageDescription={desc}", f"-UserComment={desc}",
                  f"-IPTC:Caption-Abstract={desc[:2000]}"]
            # --redo: tira as keywords da rodada anterior em todos os campos antes de gravar as novas
            d = atuais.get(str(a), {})
            protegidas = {_norm(k) for k in quadros[n].get("keywords", [])} | {"multiple-exposure"}
            for campo in CAMPOS_KW:
                atual = _lista_exif(d, campo.split(":")[1])  # exiftool -j usa o nome curto
                antigas = _keywords_ia_antigas(atual, grupos, protegidas) if args.redo else []
                ar += [f"-{campo}-={k}" for k in antigas]
                ar += _lista(campo, kws + [TAG_AI])
            lotes.append((a, ar))
            if len(lotes) >= 10:  # grava aos poucos: não perde tudo se parar no meio
                exif_gravar(lotes)
                lotes = []
        exif_gravar(lotes)
    _registrar_sugestoes(cfg, sugestoes)
    print(f"\nPronto. No digiKam, filtre a tag '{TAG_AI}', revise e remova a tag das conferidas.")
    if args.redo:
        print("Keywords trocadas nos arquivos: no digiKam, selecione as fotos e use "
              "Item > Reread Metadata From Files, senão ele mantém as tags antigas.")
