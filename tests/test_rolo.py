"""Testes sem arquivos de imagem: rode com `python3 -m unittest discover tests` na pasta do repositório."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rolo import ficha as F  # noqa: E402
from rolo.campos import args_quadro, faixa_numeros, montar_quadros, quadro_do_arquivo  # noqa: E402
from rolo.equip import Equipamentos  # noqa: E402

FIXTURE = RAIZ / "tests" / "fixtures" / "exifnotes_paulista.json"
EQUIP = RAIZ.parent / "equipment.yaml"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copy(EQUIP, self.tmp / "equipment.yaml")
        self.eq = Equipamentos(self.tmp / "equipment.yaml")
        self.rolo = {"camera": "OM1n", "film": "kodakdoublex", "lens": "zuiko50", "date": "2026-11-15",
                     "iso": 250, "title": "paulista", "count": 36, "offset": 0}

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TestExifNotes(Base):
    def test_sugestoes_usam_aliases(self):
        s = F.sugestoes_rolo(self.eq, F.ler_exifnotes(FIXTURE))
        self.assertEqual((s["camera"], s["film"], s["iso"], s["title"]), ("OM1n", "kodakdoublex", 250, "paulista"))

    def test_aliases_de_filmes_rebatizados(self):
        self.assertEqual(self.eq.procurar("films", "Sunny 400"), "kodakvision3-250d")
        self.assertEqual(self.eq.procurar("films", "Cosmos 800"), "kodakvision3-500t")

    def test_quadros(self):
        qs = F.quadros_exifnotes(self.eq, F.ler_exifnotes(FIXTURE), self.rolo, "ignore")
        q1, q8 = qs
        self.assertEqual((q1["n"], q1["lens"], q1["shutter"], q1["aperture"], q1["flash"]),
                         (1, "zuiko50", "1/60", "4.0", True))
        self.assertEqual(q1["filters"], ["Hoya Skylight 1B"])
        self.assertNotIn("date", q1)  # 17/11 está a mais de 1 dia do rolo (15/11)
        self.assertEqual((q8["n"], q8["lens"], q8["description"]), (8, "vivitar80-200", "maria"))

    def test_politica_rolo_hora(self):
        q1 = F.quadros_exifnotes(self.eq, F.ler_exifnotes(FIXTURE), self.rolo, "roll-time")[0]
        self.assertEqual(q1["date"], "2026-11-15 23:06")

    def test_offset(self):
        self.rolo["offset"] = 2
        self.assertEqual(F.quadros_exifnotes(self.eq, F.ler_exifnotes(FIXTURE), self.rolo, "ignore")[0]["n"], 3)

    def test_arquivos_invertidos(self):
        self.rolo["files_reversed"] = True
        q1, q8 = F.quadros_exifnotes(self.eq, F.ler_exifnotes(FIXTURE), self.rolo, "ignore")
        self.assertEqual((q1["n"], q8["n"]), (36, 29))  # quadro 1 do filme = último arquivo
        self.rolo["offset"] = 2
        self.assertEqual(F.quadros_exifnotes(self.eq, F.ler_exifnotes(FIXTURE), self.rolo, "ignore")[0]["n"], 34)

    def test_endereco(self):
        e = F.endereco("Av. Paulista, 1578 - Bela Vista, São Paulo - SP, 01310-200, Brazil")
        self.assertEqual(e, {"country": "Brazil", "city": "São Paulo", "state": "SP",
                             "location": "Av. Paulista, 1578", "sublocation": "Bela Vista"})


class TestFicha(Base):
    def test_prioridade_exifnotes(self):
        fi = {"roll": self.rolo,
              "ranges": [{"frames": "1-10", "source": "skill", "location": "MASP", "lat": -23.56, "lon": -46.65,
                          "lens": "zuiko28", "start": "2026-11-15 14:00", "end": "2026-11-15 15:00"}],
              "frames": [{"n": 1, "source": "exifnotes", "lens": "zuiko50", "lat": -23.54, "lon": -46.64},
                         {"n": 2, "source": "manual", "description": "x"}]}
        q = montar_quadros(fi, 36)
        self.assertEqual((q[1]["lens"], q[1]["lat"]), ("zuiko50", -23.54))
        self.assertEqual((q[2]["lens"], q[2]["description"], q[2]["location"]), ("zuiko28", "x", "MASP"))
        datas = [q[n]["date"] for n in range(1, 11)]
        self.assertEqual(datas, sorted(datas))
        self.assertTrue(datas[-1] <= "2026-11-15 15:00:00")
        self.assertNotIn("lens", q[11])

    def test_horarios_com_arquivos_invertidos(self):
        self.rolo["files_reversed"] = True
        fi = {"roll": self.rolo, "ranges": [{"frames": "27-36", "source": "skill",
                                             "start": "2026-11-15 14:00", "end": "2026-11-15 15:00"}]}
        q = montar_quadros(fi, 36)
        self.assertEqual(q[36]["date"], "2026-11-15 14:00:00")  # arquivo 36 = quadro 1 = primeiro horário
        datas = [q[n]["date"] for n in range(36, 26, -1)]
        self.assertEqual(datas, sorted(datas))
        self.assertEqual((quadro_do_arquivo(self.rolo, 1), quadro_do_arquivo(self.rolo, 36)), (36, 1))
        del self.rolo["files_reversed"]
        self.assertEqual(quadro_do_arquivo(self.rolo, 1), 1)

    def test_gravar_e_ler(self):
        fi = {"roll": self.rolo, "frames": [{"n": 3, "source": "manual", "people": ["Ana"]}]}
        F.gravar(self.tmp, fi)
        self.assertEqual(F.ler(self.tmp)["frames"][0]["people"], ["Ana"])
        self.assertEqual(F.ler(self.tmp)["roll"]["date"], "2026-11-15")  # data continua texto

    def test_faixa_numeros(self):
        self.assertEqual(faixa_numeros("1-3,7, 9-10"), [1, 2, 3, 7, 9, 10])

    def test_lente_de_outra_camera(self):
        self.rolo["camera"] = "PEN-EES2"
        args = args_quadro(self.eq, self.rolo, 1, {"lens": "zuiko50"})
        self.assertFalse(any(a.startswith("-LensModel") for a in args))  # lente fixa: sem tags de lente


class TestEquipamentos(Base):
    def test_adicionar_alias_preserva_comentarios(self):
        self.eq.adicionar_alias("lenses", "zuiko28", "28mm 2.8 Zuiko")
        self.assertEqual(self.eq.procurar("lenses", "28mm 2.8 Zuiko"), "zuiko28")
        self.assertIn("# Equipment database", (self.tmp / "equipment.yaml").read_text())



class TestConfig(Base):
    def test_resolver_prefere_inbox_ao_diretorio_atual(self):
        import os
        from unittest import mock
        from rolo.config import Config
        (self.tmp / "acervo" / "_inbox" / "rolo").mkdir(parents=True)
        (self.tmp / "cwd" / "rolo").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"FOTOS_ROOT": str(self.tmp / "acervo")}):
            cfg = Config()
        anterior = os.getcwd()
        os.chdir(self.tmp / "cwd")
        try:
            self.assertEqual(cfg.resolver("rolo", cfg.inbox), (cfg.inbox / "rolo").resolve())
            self.assertEqual(cfg.resolver("rolo"), (self.tmp / "cwd" / "rolo").resolve())
        finally:
            os.chdir(anterior)


class TestPick(unittest.TestCase):
    def test_pick(self):
        from rolo.util import pick
        self.assertEqual(pick({"PickLabel": 3, "Pick": 1}), "accepted")
        self.assertEqual(pick({"Pick": 1}), "accepted")          # só o campo do Lightroom
        self.assertEqual(pick({"PickLabel": 1, "Pick": -1}), "rejected")
        self.assertEqual(pick({"PickLabel": 2}), "pending")
        self.assertIsNone(pick({}))

    def test_portfolio_modos(self):
        from unittest import mock
        from rolo import publicar
        arqs = [Path(f"/x/{n}.tif") for n in ("aceita", "recusada", "pendente", "sem")]
        dados = {"/x/aceita.tif": {"PickLabel": 3}, "/x/recusada.tif": {"PickLabel": 1},
                 "/x/pendente.tif": {"PickLabel": 2}, "/x/sem.tif": {}}
        with mock.patch.object(publicar, "imagens", return_value=arqs), \
             mock.patch.object(publicar, "exif_ler", return_value=dados):
            self.assertEqual([a.stem for a in publicar.para_portfolio("/x", None)], ["aceita", "pendente", "sem"])
            self.assertEqual([a.stem for a in publicar.para_portfolio("/x", "accepted")], ["aceita"])


class TestVersoes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def criar(self, *nomes):
        for n in nomes:
            (self.tmp / n).touch()

    def test_edited_vence_versoes_do_digikam(self):
        from rolo.util import imagens, versao_mais_recente
        self.criar("rolo_01.tif", "rolo_01_v1.jpg", "rolo_01_v2.jpg", "rolo_01_edited.jpg", "rolo_011.tif")
        self.assertEqual([p.name for p in imagens(self.tmp)], ["rolo_01.tif", "rolo_011.tif"])
        self.assertEqual(versao_mais_recente(self.tmp / "rolo_01.tif").name, "rolo_01_edited.jpg")
        self.assertEqual(versao_mais_recente(self.tmp / "rolo_011.tif").name, "rolo_011.tif")

    def test_sem_edited_usa_maior_vN(self):
        from rolo.util import versao_mais_recente
        self.criar("rolo_02.tif", "rolo_02_v1.jpg", "rolo_02_v10.jpg", "rolo_02_v9.jpg")
        self.assertEqual(versao_mais_recente(self.tmp / "rolo_02.tif").name, "rolo_02_v10.jpg")

    def test_edited_n_do_rapidraw(self):
        from rolo.util import imagens, versao_mais_recente
        self.criar("rolo_03.tif", "rolo_03_v4.jpg", "rolo_03_edited.jpg", "rolo_03_edited_1.jpg", "rolo_03_edited_2.jpg")
        self.assertEqual([p.name for p in imagens(self.tmp)], ["rolo_03.tif"])
        self.assertEqual(versao_mais_recente(self.tmp / "rolo_03.tif").name, "rolo_03_edited_2.jpg")


class TestStatus(Base):
    def test_esperado_so_tags_conferidas(self):
        from rolo.status import _esperado
        q = {"lat": -23.5, "lon": -46.6, "city": "São Paulo", "description": "editável no digiKam"}
        e = _esperado(self.eq, self.rolo, 3, q)
        self.assertEqual((e["GPSLatitude"], e["City"], e["ImageNumber"]), ("23.5", "São Paulo", "3"))
        self.assertNotIn("ImageDescription", e)

    def test_igual(self):
        from rolo.status import _igual
        self.assertTrue(_igual("23.5530291", 23.55302909))
        self.assertTrue(_igual("2026:10:17 21:12:03", "2026:10:17 21:12:03"))
        self.assertFalse(_igual("SP", None))
        self.assertFalse(_igual("23.55", 23.56))

    def test_historico(self):
        F.registrar(self.tmp, "print", [self.tmp / "a_01.tif", self.tmp / "a_02.tif"])
        F.registrar(self.tmp, "apply")
        h = F.historico(self.tmp)
        self.assertEqual(h["print"]["files"], ["a_01", "a_02"])
        self.assertIn("at", h["apply"])


class TestIA(unittest.TestCase):
    VOCAB = {"genre": ["party", "concert"], "light": ["neon"], "subject": ["stage"]}

    def test_esquema_restringe_ao_vocabulario_com_prefixo(self):
        from rolo.ia import MAX_KW, _esquema
        kw = _esquema(self.VOCAB)["properties"]["keywords"]
        self.assertEqual(kw["items"]["enum"], ["genre:concert", "genre:party", "light:neon", "subject:stage"])
        self.assertEqual(kw["maxItems"], MAX_KW)

    def test_separar_manda_fora_da_lista_para_sugestoes(self):
        from rolo.ia import _separar
        kws, fora = _separar({"keywords": ["Genre:Party", "cups", "genre:party"], "other": ["witch-costume"]},
                             {"genre:party", "genre:concert"})
        self.assertEqual(kws, ["genre:party"])
        self.assertEqual(fora, ["cups", "witch-costume"])

    def test_redo_versao_antiga_remove_tags_simples(self):
        from rolo.ia import _keywords_ia_antigas
        atuais = ["ai:generated", "são paulo", "copos", "film:Kodak Vision3 250D", "camera:Olympus Pen EES-2",
                  "filter:amarelo", "People/Alex", "multiple-exposure", "halloween"]
        self.assertEqual(_keywords_ia_antigas(atuais, set(self.VOCAB), {"multiple-exposure", "halloween"}),
                         ["ai:generated", "são paulo", "copos"])

    def test_redo_com_prefixo_preserva_tags_simples(self):
        from rolo.ia import _keywords_ia_antigas
        atuais = ["ai:generated", "genre:party", "light:neon", "framing:old-term", "minha-tag",
                  "camera:Olympus Pen EES-2", "projeto/halloween"]
        self.assertEqual(_keywords_ia_antigas(atuais, set(self.VOCAB) | {"framing"}, set()),
                         ["ai:generated", "genre:party", "light:neon", "framing:old-term"])


class TestDocumentacao(unittest.TestCase):
    def test_cabecalho_lista_todos_os_campos(self):
        from rolo.campos import FIELDS
        faltando = [c for c in FIELDS if c not in F.CABECALHO]
        self.assertEqual(faltando, [], "campos de FIELDS ausentes do CABECALHO do roll.yaml")


if __name__ == "__main__":
    unittest.main()
