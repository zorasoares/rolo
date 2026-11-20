"""Base de equipamentos (equipment.yaml)."""
import re
from pathlib import Path

from .util import Erro, escolher, interativo, perguntar, slug
from .yamlio import carregar, carregar_texto


def _q(texto):
    """Valor YAML seguro numa lista em linha."""
    t = str(texto)
    return t if re.fullmatch(r"[\w][\w .\-/()]*", t) and not t.isdigit() else '"' + t.replace('"', '\\"') + '"'


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


class Equipamentos:
    def __init__(self, caminho):
        self.caminho = Path(caminho)
        if not self.caminho.exists():
            raise Erro(f"Base de equipamentos não encontrada: {self.caminho}")
        self.recarregar()

    def recarregar(self):
        d = carregar(self.caminho)
        self.conv = d.get("conventions", {})
        self.cameras = d.get("cameras", {})
        self.lenses = d.get("lenses", {})
        self.films = d.get("films", {})

    # ------------------------------------------------------------ consultas

    def _item(self, secao, cod, rotulo):
        tabela = getattr(self, secao)
        if cod not in tabela:
            raise Erro(f"{rotulo} '{cod}' não está em {self.caminho.name}. Opções: {', '.join(tabela)}")
        return tabela[cod]

    def camera(self, cod):
        return self._item("cameras", cod, "Câmera")

    def lente(self, cod):
        return self._item("lenses", cod, "Lente")

    def filme(self, cod):
        return self._item("films", cod, "Filme")

    def lentes_da(self, camera):
        return {k: v for k, v in self.lenses.items() if camera in v.get("cameras", []) and not v.get("fixed")}

    def digital(self, camera):
        return self.camera(camera).get("type") == "digital"

    def procurar(self, secao, texto):
        """Código cujo alias (ou nome/modelo/código) bate com o texto do Exif Notes; None se não achar."""
        if not texto:
            return None
        alvo = _norm(texto)
        for cod, item in getattr(self, secao).items():
            nomes = [cod, item.get("name", ""), item.get("model", "")] + (item.get("exifnotes_aliases") or [])
            if any(_norm(n) == alvo for n in nomes if n):
                return cod
        return None

    # ------------------------------------------------------------ escrita

    def adicionar_alias(self, secao, cod, alias):
        """Acrescenta um alias em exifnotes_aliases do item, preservando os comentários do arquivo."""
        linhas = self.caminho.read_text(encoding="utf-8").splitlines(keepends=True)
        na_secao = no_item = False
        for i, l in enumerate(linhas):
            if re.match(rf"^{secao}:\s*$", l):
                na_secao = True
                continue
            if na_secao and re.match(r"^\S", l) and not l.startswith("#"):
                break
            if na_secao and re.match(rf"^  {re.escape(cod)}:\s*$", l):
                no_item = True
                continue
            if no_item and re.match(r"^  \S", l) and not l.lstrip().startswith("#"):
                linhas.insert(i, f"    exifnotes_aliases: [{_q(alias)}]\n")
                break
            if no_item and l.strip().startswith("exifnotes_aliases:"):
                atuais = carregar_texto(l.strip())["exifnotes_aliases"] or []
                if alias not in atuais:
                    atuais.append(alias)
                    linhas[i] = "    exifnotes_aliases: [" + ", ".join(_q(a) for a in atuais) + "]\n"
                break
        else:
            if no_item:
                linhas.append(f"    exifnotes_aliases: [{_q(alias)}]\n")
        if not no_item:
            raise Erro(f"Não achei {secao}.{cod} em {self.caminho}")
        self.caminho.write_text("".join(linhas), encoding="utf-8")
        self.recarregar()

    def cadastrar_filme(self):
        print("\nCadastrar filme novo")
        nome = perguntar("  Nome completo (ex.: Kodak Portra 400)")
        cod = perguntar("  Código para a pasta", slug(nome).replace("-", ""))
        iso = perguntar("  ISO nominal", validar=int)
        tipo = escolher("  Tipo", [("color", "cor"), ("bw", "preto e branco"), ("slide", "cromo")])
        texto = self.caminho.read_text(encoding="utf-8")
        with open(self.caminho, "a", encoding="utf-8") as f:
            f.write(("" if texto.endswith("\n") else "\n") +
                    f"\n  {cod}:\n    name: {_q(nome)}\n    iso: {iso}\n    type: {tipo}\n"
                    f"    exifnotes_aliases: [{_q(nome)}]\n")
        self.recarregar()
        if cod not in self.films:
            raise Erro("O filme novo não entrou em films: (essa seção precisa ser a última do arquivo).")
        return cod

    def resolver_alias(self, secao, texto, opcoes, rotulo):
        """Acha pelo alias; se não achar e houver terminal, pergunta uma vez e salva o alias."""
        cod = self.procurar(secao, texto)
        if cod or not texto:
            return cod
        if not interativo():
            print(f"[aviso] {rotulo} '{texto}' do Exif Notes não está na base; ignorado.")
            return None
        escolha = escolher(f"{rotulo} '{texto}' (Exif Notes) não está na base. Qual é?",
                           [(k, v["name"]) for k, v in opcoes.items()], extra="ignorar")
        if escolha:
            self.adicionar_alias(secao, escolha, texto)
            print(f"  alias salvo: '{texto}' → {escolha}")
        return escolha
