"""rolo backup / check."""
import datetime as dt
import re
import sqlite3
from pathlib import Path

from .util import EXT_IMAGEM, MESES, RE_VERSAO, Erro, exif_ler, imagens, precisa, rodar


def backup(cfg, eq, args):
    db = cfg["ROLO_DIGIKAM_DB"]
    if db:
        db = Path(db).expanduser()
        if db.exists():
            destino = cfg.root / "_workflow" / "backup-digikam" / db.name
            destino.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as src, sqlite3.connect(destino) as dst:
                src.backup(dst)  # cópia consistente mesmo com o digiKam aberto
            print(f"Banco do digiKam copiado para {cfg.relativo(destino)}")
        else:
            print(f"[aviso] ROLO_DIGIKAM_DB não existe: {db}")
    remoto = cfg["ROLO_RCLONE_BACKUP"]
    if not remoto:
        print("ROLO_RCLONE_BACKUP vazio: envio para nuvem pulado.")
        return
    precisa("rclone")
    cmd = ["rclone", "sync", str(cfg.root), remoto, "--exclude", "_inbox/**", "--exclude", "_outbox/**",
           "--exclude", ".rolo.lock", "--exclude", "**/.dtrash/**", "--fast-list", "--stats-one-line", "-v"]
    if args.dry_run:
        cmd.append("--dry-run")
    # sync apaga no destino o que foi apagado aqui; --backup-dir guarda essas versões por segurança
    cmd += ["--backup-dir", f"{remoto.rstrip('/')}_lixeira/{dt.date.today():%Y-%m-%d}"]
    rodar(cmd)


RE_PASTA = re.compile(r"^(?P<data>\d{8})-(?P<resto>.+)$")


def checar(cfg, eq, args):
    alvo = cfg.resolver(args.folder) if args.folder else cfg.root
    pastas = sorted({p.parent for p in alvo.rglob("*") if p.is_file() and p.suffix.lower() in EXT_IMAGEM
                     and not any(x.startswith("_") for x in p.relative_to(cfg.root).parts)})
    def codigos(tabela):
        """[(código na pasta, código atual)], incluindo legacy_codes, do mais longo ao mais curto."""
        pares = [(c, c) for c in tabela] + [(old, c) for c, v in tabela.items() for old in v.get("legacy_codes") or []]
        return sorted(pares, key=lambda p: len(p[0]), reverse=True)

    cams, films = codigos(eq.cameras), codigos(eq.films)
    problemas_total = 0
    for pasta in pastas:
        prob = []
        rel = pasta.relative_to(cfg.root)
        m = RE_PASTA.match(pasta.name)
        camera = filme = None
        if not m:
            prob.append("nome da pasta fora do padrão AAAAMMDD-CAMERA-filme-titulo")
        else:
            try:
                data = dt.datetime.strptime(m["data"], "%Y%m%d").date()
                esperado = f"{data.year}/{data.month:02d}-{MESES[data.month - 1]}"
                if str(rel.parent) != esperado:
                    prob.append(f"deveria estar em {esperado}/")
            except ValueError:
                prob.append(f"data inválida '{m['data']}'")
            resto = m["resto"]
            par = next((p for p in cams if resto.lower().startswith(p[0].lower() + "-")), None)
            camera = par[1] if par else None
            if not camera:
                prob.append(f"câmera não reconhecida (códigos: {', '.join(eq.cameras)})")
            else:
                if par[0] != camera:
                    prob.append(f"código antigo de câmera '{par[0]}' (atual: {camera})")
                elif not resto.startswith(camera):
                    prob.append(f"câmera em caixa diferente: '{resto[:len(camera)]}' (atual: {camera})")
                if not eq.digital(camera):
                    depois = resto[len(par[0]) + 1:]
                    fp = next((p for p in films if depois.lower().startswith(p[0].lower() + "-")), None)
                    filme = fp[1] if fp else None
                    if not filme:
                        prob.append(f"filme não reconhecido em '{depois}'")
                    elif fp[0] != filme:
                        prob.append(f"código antigo de filme '{fp[0]}' (atual: {filme})")
        sidecars = [p.name for p in pasta.iterdir() if p.suffix.lower() in (".xmp", ".acr")]
        if sidecars:
            prob.append(f"{len(sidecars)} sidecar(s) .xmp/.acr")
        scripts = [p.name for p in pasta.iterdir() if p.suffix.lower() in (".bat", ".sh", ".txt")]
        if scripts:
            prob.append(f"{len(scripts)} script(s) antigo(s) ({', '.join(scripts[:2])}{'…' if len(scripts) > 2 else ''})")
        arqs = imagens(pasta)
        prefixo = re.sub(r"^\d{8}-", "", pasta.name).lower()
        fora = [a.name for a in arqs if not re.fullmatch(rf"{re.escape(prefixo)}_\d{{8}}_\d{{2,3}}", a.stem)]
        if fora:
            prob.append(f"{len(fora)}/{len(arqs)} arquivo(s) fora do padrão (ex.: {fora[0]})")
        if camera and arqs and not args.quick:
            d = exif_ler(arqs, "Make", "Model", "Artist", "DateTimeOriginal")
            cam = eq.camera(camera)
            modelos = {str(x.get("Model", "")) for x in d.values()}
            if modelos != {cam["model"]}:
                prob.append(f"Model ≠ '{cam['model']}': {sorted(modelos)}")
            sem = [k for k in ("Artist", "DateTimeOriginal") if any(not x.get(k) for x in d.values())]
            if sem:
                prob.append(f"sem {', '.join(sem)} em alguns arquivos")
        if prob:
            problemas_total += 1
            print(f"\n{rel}  ({len(arqs)} imagens)")
            for p in prob:
                print(f"   - {p}")
    print(f"\n{len(pastas)} pasta(s) verificada(s), {problemas_total} com pendências.")
