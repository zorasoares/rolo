"""Leitura/escrita YAML (PyYAML do sistema: apt install python3-yaml)."""
try:
    import yaml
except ImportError:
    raise SystemExit("[erro] PyYAML não instalado. Rode: sudo apt install python3-yaml")


class _Loader(yaml.SafeLoader):
    pass


# Datas e horários ficam como texto ("2026-11-15 14:30"); quem converte é o rolo.
_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def carregar(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader) or {}


def carregar_texto(texto):
    return yaml.load(texto, Loader=_Loader) or {}


class _Dumper(yaml.SafeDumper):
    pass


def _lista(dumper, dados):
    simples = all(not isinstance(x, (dict, list)) for x in dados)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", dados, flow_style=simples)


_Dumper.add_representer(list, _lista)


def despejar(dados):
    """YAML legível: ordem preservada, acentos, dicionários em bloco e listas simples em uma linha."""
    return yaml.dump(dados, Dumper=_Dumper, sort_keys=False, allow_unicode=True,
                     default_flow_style=False, width=100)
