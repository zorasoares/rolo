"""Ponto de entrada: rolo <comando>."""
import argparse
import sys

from . import config, ia, importar, manutencao, metadados, publicar, status
from .equip import Equipamentos
from .util import Erro

AJUDA = """\
Fluxo de um rolo:
  rolo import [PASTA]         menu: câmera/filme/lente da base → pasta, nomes, DNG, EXIF base
                              (PASTA fora de _inbox/ é copiada; dentro, movida)
  (digiKam)                   classificar: nota, pick (recusadas ficam de fora), etiqueta verde (gráfica)
  rolo print FOLDER           exporta as verdes e envia para o Drive da gráfica
  rolo sheet FOLDER --exifnotes X.json
                              monta o roll.yaml com o Exif Notes; complete com a skill roll-sheet
  rolo apply FOLDER           grava o roll.yaml nos arquivos (e reindexa o PhotoPrism)
  rolo albums FOLDER          exporta as não recusadas ainda não enviadas, um álbum por sessão
                              ("Analog - 2026 Halloween") → Immich + Google Photos, uma vez só
  rolo ai FOLDER              descrições por IA (Ollama) onde ainda falta (opcional)
  (digiKam)                   revisar a tag ai:generated

Onde estou: rolo status [FOLDER]
Outros: rolo backup | rolo check [FOLDER] | rolo config
FOLDER pode ser relativa ao acervo (2026/11-novembro/...) ou ao diretório atual.
"""


def montar_parser():
    p = argparse.ArgumentParser(prog="rolo", description="Fluxo de fotografia analógica e digital.",
                                epilog=AJUDA, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", metavar="command")

    sub.add_parser("config", help="mostra a configuração ativa nesta máquina")

    s = sub.add_parser("status", help="em que etapa do fluxo cada rolo está (sem FOLDER: todos os rolos pendentes)")
    s.add_argument("folder", nargs="?", help="pasta do rolo (padrão: a pasta atual, se tiver roll.yaml)")
    s.add_argument("--all", action="store_true", help="no panorama, mostra também os rolos concluídos")

    s = sub.add_parser("import", help="cria a pasta do rolo, renomeia e grava o EXIF base")
    s.add_argument("inbox", nargs="?", help="pasta com os scans: em _inbox/ (movida) ou qualquer outra, ex.: . (copiada); "
                                             "sem isso, menu com as pastas de _inbox/")
    s.add_argument("--camera", help="código da câmera (equipment.yaml)")
    s.add_argument("--film", help="código do filme")
    s.add_argument("--lens", help="código da lente padrão")
    s.add_argument("--iso", type=int, help="ISO do rolo (push/pull); padrão = ISO do filme")
    s.add_argument("--date", help="data do rolo AAAA-MM-DD")
    s.add_argument("--title", help="título (vira parte do nome da pasta)")
    s.add_argument("--reversed", action=argparse.BooleanOptionalAction, default=None,
                   help="scans em ordem invertida (último arquivo = quadro 1): renomeia na ordem do filme "
                        "(sem a flag, pergunta)")
    s.add_argument("--exifnotes", help="JSON do Exif Notes, só para sugerir câmera/filme/título no menu")

    s = sub.add_parser("sheet", help="cria/atualiza o roll.yaml a partir do Exif Notes")
    s.add_argument("folder")
    s.add_argument("--exifnotes", help="JSON exportado do Exif Notes")
    s.add_argument("--dates", choices=["ignore", "roll-time", "keep"],
                   help="datas do Exif Notes a mais de 1 dia do rolo (padrão: pergunta)")
    s.add_argument("--offset", type=int, help="arquivo = quadro do Exif Notes + N (se o lab numerou diferente)")
    s.add_argument("--reversed", action=argparse.BooleanOptionalAction, default=None,
                   help="pasta importada sem corrigir scans invertidos: o último arquivo é o quadro 1 "
                        "(sem a flag e sem scan_order na ficha, pergunta)")

    s = sub.add_parser("apply", help="grava o roll.yaml nos arquivos")
    s.add_argument("folder")
    s.add_argument("--dry-run", action="store_true", help="mostra os argumentos sem gravar")
    s.add_argument("--show", type=int, default=3, help="quantos arquivos mostrar no dry-run")

    s = sub.add_parser("ai", help="título/descrição/keywords por IA local onde falta descrição (ignora recusadas)")
    s.add_argument("folder")
    s.add_argument("--redo", action="store_true", help="refaz também as que ainda têm ai:generated, trocando as keywords antigas da IA "
                        "(as com prefixo de grupo do tags.yaml; tags simples só saem em fotos da versão antiga)")
    s.add_argument("--limit", type=int, help="processa no máximo N fotos (teste)")

    s = sub.add_parser("print", help="exporta as fotos com a etiqueta da gráfica e envia")
    s.add_argument("folder")
    s.add_argument("--no-upload", action="store_true", help="só exporta para _outbox/")

    s = sub.add_parser("albums", aliases=["portfolio"],
                       help="exporta as fotos não recusadas ainda não enviadas, um álbum por sessão, e envia uma vez "
                            "ao Immich e ao Google Photos")
    s.add_argument("folder")
    s.add_argument("--dry-run", action="store_true", help="exporta e confere no staging, mas não envia nem registra")
    s.add_argument("--force", action="store_true", help="exporta mesmo com EXIF incompleto")

    s = sub.add_parser("backup", help="backup do acervo (rclone) e do banco do digiKam")
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("check", help="lista pastas/arquivos fora do padrão")
    s.add_argument("folder", nargs="?")
    s.add_argument("--quick", action="store_true", help="não lê o EXIF, só os nomes")
    return p


COMANDOS = {
    "import": importar.executar, "sheet": metadados.ficha,
    "apply": metadados.aplicar, "ai": ia.executar, "print": publicar.grafica,
    "albums": publicar.albums, "portfolio": publicar.albums, "backup": manutencao.backup, "check": manutencao.checar,
    "status": status.executar,
}


def main(argv=None):
    parser = montar_parser()
    args = parser.parse_args(argv)
    if not args.comando:
        parser.print_help()
        return 0
    try:
        cfg = config.Config()
        if args.comando == "config":
            config.mostrar(cfg)
            return 0
        eq = Equipamentos(cfg["ROLO_EQUIPMENT"])
        COMANDOS[args.comando](cfg, eq, args)
        return 0
    except Erro as e:
        print(f"\n[erro] {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrompido", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
