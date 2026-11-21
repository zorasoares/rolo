"""Configuração do rolo.

Ordem de prioridade: variável de ambiente > ~/.config/rolo/config.yaml > padrão.
A mesma instalação roda no servidor e no PC; só muda a configuração.
"""
import os
import sys
from pathlib import Path

ARQUIVO = Path(os.environ.get("ROLO_CONFIG", "~/.config/rolo/config.yaml")).expanduser()

# chave -> (padrão, descrição)
CHAVES = {
    "FOTOS_ROOT": ("/srv/data/fotos", "raiz do acervo (no PC: o ponto de montagem NFS)"),
    "ROLO_INBOX": ("{FOTOS_ROOT}/_inbox", "onde chegam os downloads do lab e os JSON do Exif Notes"),
    "ROLO_OUTBOX": ("{FOTOS_ROOT}/_outbox", "JPGs exportados para a gráfica (print/) e os álbuns (albuns/)"),
    "ROLO_EQUIPMENT": ("{FOTOS_ROOT}/_workflow/equipment.yaml", "base de câmeras, lentes e filmes"),
    "ROLO_TAGS": ("{FOTOS_ROOT}/_workflow/tags.yaml", "vocabulário de tags que `rolo ai` pode usar"),
    "OLLAMA_HOST": ("http://localhost:11434", "servidor Ollama usado por `rolo ai`"),
    "ROLO_AI_MODEL": ("qwen2.5vl:7b", "modelo de visão do Ollama"),
    "ROLO_RCLONE_LAB": ("drive:", "remoto rclone usado para baixar as pastas compartilhadas do lab"),
    "ROLO_RCLONE_PRINT": ("drive:Gráfica", "destino dos JPGs da gráfica"),
    "ROLO_GPHOTOS": ("gphotos:", "remoto rclone do Google Photos; cada álbum vai em album/<nome> (vazio = não enviar)"),
    "ROLO_RCLONE_BACKUP": ("drive:Fotos", "destino do backup completo (vazio = não enviar)"),
    "ROLO_IMMICH": ("on", "envia os álbuns ao Immich: on ou vazio (requer `immich login`)"),
    "ROLO_PHOTOPRISM_INDEX_CMD": ("", "comando para reindexar uma pasta; {folder} = caminho relativo ao acervo"),
    "ROLO_DIGIKAM_DB": ("", "arquivo digikam4.db (só no PC) para incluir no backup"),
}

# chaves antigas -> nova (vazia na antiga = destino desligado também na nova)
ANTIGAS = {"ROLO_RCLONE_GPHOTOS": "ROLO_GPHOTOS", "ROLO_IMMICH_ALBUM": "ROLO_IMMICH"}


def _carregar_arquivo():
    if ARQUIVO.exists():
        from .yamlio import carregar
        # chave antiga sem valor (ROLO_IMMICH_ALBUM:) conta como vazia: era o jeito de desligar o envio
        return {k.upper(): "" if v is None else str(v) for k, v in carregar(ARQUIVO).items()
                if v is not None or k.upper() in ANTIGAS}
    return {}


class Config:
    def __init__(self):
        arquivo = _carregar_arquivo()
        self.origem = {}
        brutos = {}
        for chave, (padrao, _) in CHAVES.items():
            if chave in os.environ:
                brutos[chave], self.origem[chave] = os.environ[chave], "ambiente"
            elif chave in arquivo:
                brutos[chave], self.origem[chave] = arquivo[chave], "config.yaml"
            else:
                brutos[chave], self.origem[chave] = padrao, "padrão"
        for antiga, nova in ANTIGAS.items():
            if antiga in os.environ or antiga in arquivo:
                valor = os.environ.get(antiga, arquivo.get(antiga))
                print(f"[aviso] {antiga} não é mais usada; use {nova} (veja `rolo config`).", file=sys.stderr)
                if not valor.strip() and self.origem[nova] == "padrão":
                    brutos[nova], self.origem[nova] = "", antiga
        root = os.path.expanduser(brutos["FOTOS_ROOT"])
        self.valores = {k: os.path.expanduser(v.replace("{FOTOS_ROOT}", root)) for k, v in brutos.items()}

    def __getitem__(self, chave):
        return self.valores[chave]

    @property
    def root(self):
        return Path(self["FOTOS_ROOT"])

    @property
    def inbox(self):
        return Path(self["ROLO_INBOX"])

    @property
    def outbox(self):
        return Path(self["ROLO_OUTBOX"])

    def resolver(self, caminho, *bases):
        """Aceita caminho absoluto, relativo a `bases` (nesta ordem), ao diretório atual ou ao acervo."""
        p = Path(caminho).expanduser()
        if p.is_absolute():
            return p.resolve()
        for base in bases:
            if (Path(base) / p).exists():
                return (Path(base) / p).resolve()
        if p.exists():
            return p.resolve()
        return (self.root / p).resolve()

    def relativo(self, caminho):
        try:
            return Path(caminho).resolve().relative_to(self.root.resolve())
        except ValueError:
            return Path(caminho)


def mostrar(cfg):
    print(f"Arquivo de config: {ARQUIVO} ({'existe' if ARQUIVO.exists() else 'não existe'})\n")
    for chave, (_, desc) in CHAVES.items():
        print(f"{chave:28} = {cfg[chave] or '(vazio)'}")
        print(f"{'':28}   [{cfg.origem[chave]}] {desc}")
