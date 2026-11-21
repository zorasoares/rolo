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
        # lente fixa: sempre a dela, mesmo com outra lente no quadro
        self.assertIn("-LensModel=D.Zuiko 30mm f/2.8", args)
        self.assertIn("-FocalLength=30", args)
        self.assertFalse(any("Zuiko 50mm" in a for a in args))


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
        (self.tmp / "acervo" / "rolo").mkdir()  # para "../rolo" a partir de _inbox/ existir e precisar ser ignorado
        with mock.patch.dict(os.environ, {"FOTOS_ROOT": str(self.tmp / "acervo")}):
            cfg = Config()
        anterior = os.getcwd()
        os.chdir(self.tmp / "cwd")
        try:
            self.assertEqual(cfg.resolver("rolo", cfg.inbox), (cfg.inbox / "rolo").resolve())
            self.assertEqual(cfg.resolver("rolo"), (self.tmp / "cwd" / "rolo").resolve())
            # explicitamente relativo: sempre o diretório atual, mesmo existindo em _inbox/
            self.assertEqual(cfg.resolver("./rolo", cfg.inbox), (self.tmp / "cwd" / "rolo").resolve())
            self.assertEqual(cfg.resolver(".", cfg.inbox), (self.tmp / "cwd").resolve())
            os.chdir(self.tmp / "cwd" / "rolo")
            self.assertEqual(cfg.resolver("../rolo", cfg.inbox), (self.tmp / "cwd" / "rolo").resolve())
        finally:
            os.chdir(anterior)


class TestImportar(Base):
    """Dentro de _inbox/ os scans são movidos e a subpasta vazia é apagada; fora, copiados e a origem fica."""

    def importar(self, origem, criar=True):
        import argparse
        import os
        from unittest import mock
        from rolo import importar
        from rolo.config import Config
        with mock.patch.dict(os.environ, {"FOTOS_ROOT": str(self.tmp / "acervo")}):
            cfg = Config()
        cfg.inbox.mkdir(parents=True, exist_ok=True)
        origem = origem(cfg)
        if criar:
            origem.mkdir(parents=True, exist_ok=True)
            for n in (1, 2):
                (origem / f"scan{n}.jpg").write_bytes(b"x")
        args = argparse.Namespace(inbox=str(origem), exifnotes=None, camera="OM1n", film="kodakgold200",
                                  lens=None, iso=None, date="2026-11-15", title="teste", reversed=False)
        with mock.patch.object(importar, "precisa"), mock.patch.object(importar, "interativo", return_value=False), \
             mock.patch.object(importar, "exif_gravar"):
            destino = importar.executar(cfg, self.eq, args)
        self.assertEqual(len(list(destino.glob("*.jpg"))), 2)
        return cfg, origem

    def test_fora_de_inbox_copia_e_mantem_origem(self):
        _, origem = self.importar(lambda cfg: self.tmp / "downloads" / "rolo12")
        self.assertEqual(sorted(p.name for p in origem.iterdir()), ["scan1.jpg", "scan2.jpg"])

    def test_subpasta_de_inbox_move_e_apaga(self):
        _, origem = self.importar(lambda cfg: cfg.inbox / "rolo12")
        self.assertFalse(origem.exists())

    def test_raiz_de_inbox_move_mas_nao_apaga(self):
        cfg, origem = self.importar(lambda cfg: cfg.inbox)
        self.assertTrue(cfg.inbox.is_dir())
        self.assertEqual(list(origem.glob("*.jpg")), [])

    def test_pasta_inexistente_e_erro(self):
        from rolo.util import Erro
        with self.assertRaises(Erro):
            self.importar(lambda cfg: self.tmp / "nao-existe", criar=False)


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


class TestAlbuns(Base):
    def setUp(self):
        super().setUp()
        # vintage na cópia do equipment (independe do equipment.yaml real)
        for cod in ("zuiko28", "zuiko50"):
            self.eq.lenses[cod]["vintage"] = True
            self.eq.lenses[cod]["cameras"] = ["OM1n", "EM5II"]
        self.digital = {"camera": "EM5II", "date": "2026-10-31", "title": "festa", "count": 10}

    def test_prefixo_filme(self):
        from rolo.campos import album_de
        fi = {"roll": self.rolo, "ranges": [{"frames": "1-14", "album": "2026 Halloween"},
                                            {"frames": "15-36", "album": "2026 Eleições", "personal": True}]}
        q = montar_quadros(fi, 36)
        self.assertEqual(album_de(self.eq, self.rolo, 3, q[3]), "Analog - 2026 Halloween")
        self.assertEqual(album_de(self.eq, self.rolo, 20, q[20]), "Analog - 2026 Eleições")  # personal no filme: Analog

    def test_padrao_sem_album(self):
        from rolo.campos import album_de
        self.assertEqual(album_de(self.eq, self.rolo, 1, {}), "Analog - 2026 paulista")
        self.assertEqual(album_de(self.eq, self.digital, 1, {}), "Photography - 2026 festa")

    def test_digital_lentes_misturadas(self):
        from rolo.campos import album_de
        fi = {"roll": self.digital, "ranges": [{"frames": "1-4", "lens": "zuiko50", "album": "2026 Halloween"},
                                               {"frames": "5-10", "album": "2026 Halloween"}]}
        q = montar_quadros(fi, 10)
        self.assertEqual({album_de(self.eq, self.digital, n, q[n]) for n in q},
                         {"Vintage - 2026 Halloween", "Photography - 2026 Halloween"})
        self.assertEqual(album_de(self.eq, self.digital, 1, {**q[1], "personal": True}), "2026 Halloween")

    def test_digital_grava_lente_explicita(self):
        args = args_quadro(self.eq, self.digital, 1, {"lens": "zuiko50", "album": "2026 Halloween", "personal": True})
        self.assertIn("-LensModel=Zuiko 50mm f/1.4", args)
        self.assertIn("-XMP-iptcExt:Event=2026 Halloween", args)
        self.assertIn("-XMP-dc:Subject+=personal", args)
        self.assertFalse(any(a.startswith("-LensModel") for a in args_quadro(self.eq, self.digital, 2, {})))
        self.assertFalse(any(a.startswith("-DateTimeOriginal") for a in args))  # data continua a da câmera

    def test_digital_ignora_lente_do_rolo(self):
        self.digital["lens"] = "vivitar80-200"  # `rolo import --lens` num rolo digital
        self.eq.lenses["vivitar80-200"]["cameras"] = ["OM1n"]
        args = args_quadro(self.eq, self.digital, 1, {})
        self.assertFalse(any(a.startswith("-LensModel") for a in args))  # fica a lente gravada pela câmera
        from rolo.campos import album_de
        self.assertEqual(album_de(self.eq, self.digital, 1, {}), "Photography - 2026 festa")
        self.rolo["lens"] = "zuiko28"  # no filme, a lente do rolo continua valendo
        self.assertIn("-LensModel=Zuiko 28mm f/2.8", args_quadro(self.eq, self.rolo, 1, {}))

    def test_sem_album_nem_personal_limpa(self):
        args = args_quadro(self.eq, self.rolo, 1, {})
        self.assertIn("-XMP-iptcExt:Event=", args)
        self.assertIn("-XMP-dc:Subject-=personal", args)
        args = args_quadro(self.eq, self.rolo, 1, {"album": "2026 X", "personal": True})
        self.assertNotIn("-XMP-dc:Subject-=personal", args[-1:])
        self.assertIn("-XMP-dc:Subject+=personal", args)

    def test_ligado(self):
        from rolo.util import ligado
        for v in ("", None, False, "false", "OFF", "No", "0", 0, " off "):
            self.assertFalse(ligado(v), v)
        for v in ("on", True, "gphotos:", "1", "yes"):
            self.assertTrue(ligado(v), v)

    def test_config_chave_antiga_vazia_desliga(self):
        import io
        import os
        from contextlib import redirect_stderr
        from unittest import mock
        from rolo.config import Config
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"ROLO_IMMICH_ALBUM": "", "ROLO_RCLONE_GPHOTOS": "gphotos:album/X"}), \
             mock.patch("rolo.config.ARQUIVO", self.tmp / "sem-config.yaml"), redirect_stderr(err):
            os.environ.pop("ROLO_IMMICH", None)
            os.environ.pop("ROLO_GPHOTOS", None)
            cfg = Config()
        self.assertEqual(cfg["ROLO_IMMICH"], "")
        self.assertEqual(cfg["ROLO_GPHOTOS"], "gphotos:")  # antiga com valor: só avisa
        self.assertIn("use ROLO_IMMICH", err.getvalue())
        self.assertIn("use ROLO_GPHOTOS", err.getvalue())

    def test_lente_vintage_em_camera_nao_listada(self):
        from rolo.util import Erro
        self.eq.lenses["vivitar80-200"]["cameras"] = ["OM1n"]
        with self.assertRaises(Erro) as ctx:
            args_quadro(self.eq, self.digital, 1, {"lens": "vivitar80-200"})
        self.assertIn("EM5II", str(ctx.exception))

    def test_historico_une_arquivos_e_albuns(self):
        F.registrar(self.tmp, "albums", ["a_01", "a_02"], unir=True, albuns={"Analog - X": ["a_01", "a_02"]})
        F.registrar(self.tmp, "albums", ["a_03"], unir=True, albuns={"Analog - Y": ["a_03"]})
        h = F.historico(self.tmp)["albums"]
        self.assertEqual(h["files"], ["a_01", "a_02", "a_03"])
        self.assertEqual(h["albums"], {"Analog - X": ["a_01", "a_02"], "Analog - Y": ["a_03"]})
        F.registrar(self.tmp, "print", ["b_01"])
        F.registrar(self.tmp, "print", ["b_02"])  # sem unir: substitui
        self.assertEqual(F.historico(self.tmp)["print"]["files"], ["b_02"])

    def test_tira_campos_da_ia(self):
        from rolo.publicar import args_sem_ia
        d = {"Subject": ["ai:generated", "genre:party", "film:Kodak Gold 200", "halloween", "People/Ana"],
             "TagsList": ["ai:generated", "light:neon"], "HierarchicalSubject": "ai:generated", "Keywords": []}
        args = args_sem_ia(d, {"genre", "light"}, {"title": "Festa"})
        self.assertIn("-XMP-dc:Title=Festa", args)                # título do roll.yaml fica
        self.assertIn("-XMP-dc:Description=", args)               # descrição da IA sai
        self.assertIn("-XMP-dc:Subject-=ai:generated", args)
        self.assertIn("-XMP-dc:Subject-=genre:party", args)
        self.assertIn("-XMP-digiKam:TagsList-=light:neon", args)
        self.assertIn("-XMP-lr:HierarchicalSubject-=ai:generated", args)
        self.assertFalse(any(k in a for a in args for k in ("film:", "halloween", "People/")))

    def test_status_apply_depois_do_envio(self):
        from rolo.status import OK, PENDENTE, etapa_albuns
        eleg = [Path("/x/a_01.tif"), Path("/x/a_02.tif")]
        hist = {"albums": {"at": "2026-11-20 10:00", "files": ["a_01", "a_02"], "albums": {"Analog - X": ["a_01", "a_02"]}},
                "apply": {"at": "2026-11-20 11:00"}}
        e = etapa_albuns(hist, eleg, "r")
        self.assertEqual(e.estado, OK)
        self.assertIn("dados antigos no Immich/Google", e.detalhe)
        self.assertEqual(etapa_albuns({"portfolio": {"at": "2026-01-01 00:00", "files": ["a_01", "a_02"]}},
                                      eleg, "r").estado, OK)  # portfolio legado conta como enviado
        e = etapa_albuns({"albums": {"at": "2026-11-20 10:00", "files": ["a_01"]}}, eleg, "r")
        self.assertEqual((e.estado, e.detalhe.split()[0]), (PENDENTE, "1"))
        self.assertEqual(etapa_albuns({}, eleg, "r").estado, PENDENTE)

    def test_remoto_gphotos(self):
        from rolo.publicar import _remoto_gphotos
        self.assertEqual(_remoto_gphotos("gphotos:", "Analog - X"), "gphotos:album/Analog - X")
        self.assertEqual(_remoto_gphotos("gphotos:fotos", "Y"), "gphotos:fotos/album/Y")


class TestEnvioAlbuns(Base):
    """rolo albums com exportação e envio simulados: o que é enviado, para onde e o que fica registrado."""

    class Cfg:
        def __init__(self, tmp, **valores):
            self.outbox = tmp / "_outbox"
            self.valores = {"ROLO_IMMICH": "on", "ROLO_GPHOTOS": "gphotos:", **valores}

        def __getitem__(self, chave):
            return self.valores[chave]

        def resolver(self, caminho, *bases):
            return Path(caminho)

        def relativo(self, caminho):
            return Path(caminho)

    def setUp(self):
        super().setUp()
        from unittest import mock
        from rolo import publicar
        self.pasta = self.tmp / "rolo"
        self.pasta.mkdir()
        self.arqs = [self.pasta / f"r_{n:02}.tif" for n in range(1, 5)]
        for a in self.arqs:
            a.touch()
        self.rolo["count"] = 4
        F.gravar(self.pasta, {"roll": self.rolo, "ranges": [{"frames": "1-2", "album": "2026 Halloween"},
                                                            {"frames": "3-4", "album": "2026 Eleições"}]})
        self.selecao = list(self.arqs)
        self.comandos = []
        for alvo, efeito in (("para_portfolio", lambda pasta, modo: list(self.selecao)),
                             ("exportar", lambda a, destino, lado, q: destino.touch()),
                             ("_conferir", lambda a, jpg: []),
                             ("precisa", lambda *p: None),
                             ("rodar", lambda cmd, **kw: self.comandos.append(cmd))):
            m = mock.patch.object(publicar, alvo, side_effect=efeito)
            m.start()
            self.addCleanup(m.stop)

    def rodar_albums(self, cfg=None, dry_run=False, force=False):
        from types import SimpleNamespace
        from rolo.publicar import albums
        self.comandos.clear()
        albums(cfg or self.Cfg(self.tmp), self.eq, SimpleNamespace(folder=self.pasta, dry_run=dry_run, force=force))

    def conferir(self, problemas):
        """_conferir devolve `problemas` para r_02 e nada para as outras."""
        from unittest import mock
        from rolo import publicar
        m = mock.patch.object(publicar, "_conferir", side_effect=lambda a, jpg: problemas if a.stem == "r_02" else [])
        m.start()
        self.addCleanup(m.stop)

    def test_destinos_desligados_por_off_false_no_0(self):
        for valor in ("off", "False", "no", "0", ""):
            self.selecao = list(self.arqs)
            (self.pasta / ".rolo-history.yaml").unlink(missing_ok=True)
            self.rodar_albums(self.Cfg(self.tmp, ROLO_IMMICH=valor))
            self.assertEqual({c[0] for c in self.comandos}, {"rclone"}, valor)

    def test_share_false_como_texto(self):
        self.rolo["share"] = "false"
        F.gravar(self.pasta, {"roll": self.rolo, "ranges": []})
        self.rodar_albums()
        self.assertEqual(self.comandos, [])

    def test_sem_destino_nao_registra(self):
        self.rodar_albums(self.Cfg(self.tmp, ROLO_IMMICH="", ROLO_GPHOTOS=""))
        self.assertEqual(self.comandos, [])
        self.assertNotIn("albums", F.historico(self.pasta))
        self.rodar_albums()  # destino ligado depois: envia tudo
        self.assertEqual(len([c for c in self.comandos if c[0] == "immich"]), 2)
        self.assertEqual(F.historico(self.pasta)["albums"]["files"], ["r_01", "r_02", "r_03", "r_04"])

    def test_ia_nao_revisada_sai_sem_campos_da_ia_e_e_enviada(self):
        from unittest import mock
        from rolo import publicar
        self.conferir(["descrição da IA ainda não revisada (tag ai:generated)"])
        gravados = []
        with mock.patch.object(publicar, "exif_ler", return_value={}) as ler, \
             mock.patch.object(publicar, "exif_gravar", side_effect=gravados.extend), \
             mock.patch.object(publicar, "_vocabulario", return_value={"genre": ["party"]}):
            ler.side_effect = lambda arqs, *t: {str(arqs[0]): {"Subject": ["ai:generated", "genre:party"]}}
            self.rodar_albums()
        self.assertEqual([jpg.name for jpg, _ in gravados], ["r_02.jpg"])
        self.assertIn("-XMP-dc:Subject-=ai:generated", gravados[0][1])
        self.assertIn("-XMP-dc:Subject-=genre:party", gravados[0][1])
        self.assertIn("r_02", F.historico(self.pasta)["albums"]["files"])
        final = self.tmp / "_outbox" / "albuns" / "Analog - 2026 Halloween"
        self.assertTrue((final / "r_02.jpg").exists())

    def test_exif_incompleto_bloqueia_ate_corrigir(self):
        self.conferir(["faltou GPSLatitude"])
        self.rodar_albums()
        self.assertNotIn("r_02", F.historico(self.pasta)["albums"]["files"])
        self.assertFalse((self.tmp / "_outbox" / "albuns" / "Analog - 2026 Halloween" / "r_02.jpg").exists())
        self.conferir([])
        self.rodar_albums()
        self.assertEqual([c[3] for c in self.comandos if c[0] == "immich"], ["Analog - 2026 Halloween"])
        self.assertIn("r_02", F.historico(self.pasta)["albums"]["files"])

    def test_exif_incompleto_com_force(self):
        self.conferir(["faltou GPSLatitude"])
        self.rodar_albums(force=True)
        self.assertIn("r_02", F.historico(self.pasta)["albums"]["files"])
        self.assertTrue((self.tmp / "_outbox" / "albuns" / "Analog - 2026 Halloween" / "r_02.jpg").exists())

    def test_envia_um_album_por_sessao(self):
        self.rodar_albums()
        albuns_immich = sorted(c[3] for c in self.comandos if c[0] == "immich")
        self.assertEqual(albuns_immich, ["Analog - 2026 Eleições", "Analog - 2026 Halloween"])
        remotos = sorted(c[3] for c in self.comandos if c[0] == "rclone")
        self.assertEqual(remotos, ["gphotos:album/Analog - 2026 Eleições", "gphotos:album/Analog - 2026 Halloween"])
        final = self.tmp / "_outbox" / "albuns" / "Analog - 2026 Halloween"
        self.assertEqual(sorted(p.name for p in final.iterdir()), ["r_01.jpg", "r_02.jpg"])
        self.assertEqual(F.historico(self.pasta)["albums"]["files"], ["r_01", "r_02", "r_03", "r_04"])

    def test_segunda_execucao_envia_so_as_novas(self):
        self.selecao = self.arqs[:3]
        self.rodar_albums()
        self.selecao = list(self.arqs)
        self.rodar_albums()
        self.assertEqual([c[3] for c in self.comandos if c[0] == "immich"], ["Analog - 2026 Eleições"])
        enviados = [p.name for p in (self.tmp / "_outbox" / "albuns" / "Analog - 2026 Eleições").iterdir()]
        self.assertEqual(sorted(enviados), ["r_03.jpg", "r_04.jpg"])
        self.rodar_albums()
        self.assertEqual(self.comandos, [])  # nada novo

    def test_destino_desligado(self):
        self.rodar_albums(self.Cfg(self.tmp, ROLO_GPHOTOS=""))
        self.assertEqual({c[0] for c in self.comandos}, {"immich"})

    def test_share_false_so_exporta(self):
        self.rolo["share"] = False
        F.gravar(self.pasta, {"roll": self.rolo, "ranges": []})
        self.rodar_albums()
        self.assertEqual(self.comandos, [])
        self.assertTrue((self.tmp / "_outbox" / "albuns" / "Analog - 2026 paulista" / "r_01.jpg").exists())

    def test_dry_run_nao_envia_nem_registra(self):
        self.rodar_albums(dry_run=True)
        self.assertEqual(self.comandos, [])
        self.assertNotIn("albums", F.historico(self.pasta))


class TestAdotar(Base):
    """rolo adopt: roll.yaml a partir do nome da pasta e do EXIF existente, fotos dadas como já enviadas."""

    def setUp(self):
        super().setUp()
        import os
        from unittest import mock
        from rolo.config import Config
        with mock.patch.dict(os.environ, {"FOTOS_ROOT": str(self.tmp / "acervo")}):
            self.cfg = Config()
        self.pasta = self.cfg.root / "2026" / "08-agosto" / "20260801-OM1n-sunny400-serra-negra"
        self.pasta.mkdir(parents=True)
        self.arqs = [self.pasta / f"om1n-sunny400-serra-negra_20260801_{n:02}.jpg" for n in (1, 2, 3)]
        for a in self.arqs:
            a.touch()
        self.exif = {str(self.arqs[0]): {"DateTimeOriginal": "2026:08:01 10:15:00", "LensModel": "Zuiko 28mm f2.8",
                                         "GPSLatitude": -22.6, "GPSLongitude": -46.7, "City": "Serra Negra",
                                         "ISO": 400, "Subject": ["personal", "film:Sunny 400"]},
                     str(self.arqs[1]): {"LensModel": "Olympus Zuiko 50mm f1.4", "ISO": 400, "Event": "2026 Serra"},
                     str(self.arqs[2]): {"LensModel": "Zuiko 28mm f2.8", "ISO": 400}}
        self.aplicados = []

    def adotar(self, pasta=None, **kw):
        from unittest import mock
        from rolo import adotar
        with mock.patch.object(adotar, "exif_ler", return_value=self.exif), \
             mock.patch.object(adotar, "aplicar", side_effect=lambda cfg, eq, a: self.aplicados.append(a.folder)):
            adotar.adotar(self.cfg, self.eq, pasta or self.pasta, **kw)

    def test_nome_com_codigos_antigos(self):
        from rolo.manutencao import ler_nome
        n = ler_nome(self.eq, "20260510-PEN-EES-2-Sunny400-VoltaRio")
        self.assertEqual((n["camera"], n["film"], n["title"], n["camera_legado"], n["film_legado"]),
                         ("PEN-EES2", "kodakvision3-250d", "VoltaRio", True, True))
        n = ler_nome(self.eq, "20260913-E-M5MarkII-itororo")
        self.assertEqual((n["camera"], n["film"], n["title"]), ("EM5II", None, "itororo"))
        self.assertIsNone(ler_nome(self.eq, "2021025-OM1n-kodakdoublex-eleicoes"))

    def test_lente_aceita_marca_na_frente(self):
        from rolo.adotar import lente_do_exif
        self.assertEqual(lente_do_exif(self.eq, "OM1n", "Zuiko 50mm f1.4"), "zuiko50")
        self.assertEqual(lente_do_exif(self.eq, "OM1n", "Olympus Zuiko 28mm f2.8"), "zuiko28")
        self.assertEqual(lente_do_exif(self.eq, "OM1n", "Vivitar Vivitar 80-200mm f4.5"), "vivitar80-200")
        self.assertIsNone(lente_do_exif(self.eq, "OM1n", "D.Zuiko 30mm f2.8"))  # lente fixa da PEN

    def test_ficha_vem_do_exif_e_fotos_ficam_enviadas(self):
        self.adotar()
        fi = F.ler(self.pasta)
        rolo = fi["roll"]
        self.assertEqual((rolo["camera"], rolo["film"], rolo["lens"], rolo["iso"], rolo["date"], rolo["count"]),
                         ("OM1n", "kodakvision3-250d", "zuiko28", 400, "2026-08-01", 3))
        q = {x["n"]: x for x in fi["frames"]}
        self.assertEqual((q[1]["date"], q[1]["lat"], q[1]["city"], q[1]["personal"], q[1]["source"]),
                         ("2026-08-01 10:15:00", -22.6, "Serra Negra", True, "adopt"))
        self.assertEqual((q[2]["lens"], q[2]["album"]), ("zuiko50", "2026 Serra"))
        self.assertNotIn(3, q)  # nada além da lente do rolo
        h = F.historico(self.pasta)
        self.assertEqual(h["portfolio"]["files"], sorted(a.stem for a in self.arqs))
        self.assertEqual(self.aplicados, [str(self.pasta)])

    def test_zoom_guarda_focal_do_arquivo(self):
        self.exif[str(self.arqs[1])].update({"LensModel": "Vivitar Vivitar 80-200mm f4.5", "FocalLength": 80.0})
        self.exif[str(self.arqs[2])].update({"LensModel": "Vivitar 80-200mm f/4.5", "FocalLength": 200.0})
        self.adotar()
        fi = F.ler(self.pasta)
        q = {x["n"]: x for x in fi["frames"]}
        self.assertEqual((fi["roll"]["lens"], q[1]["lens"], q[2]["focal_length"]), ("vivitar80-200", "zuiko28", 80))
        self.assertNotIn(3, q)  # 200 é a focal padrão da lente do rolo

    def test_unsent_dry_run_e_sem_apply(self):
        self.adotar(enviadas=False, padronizar=False)
        self.assertNotIn("portfolio", F.historico(self.pasta))
        self.assertEqual(self.aplicados, [])
        F.caminho(self.pasta).unlink()
        self.adotar(simular=True)
        self.assertFalse(F.caminho(self.pasta).exists())
        self.assertEqual(self.aplicados, [])

    def test_recusa(self):
        from rolo.util import Erro
        self.adotar()
        with self.assertRaisesRegex(Erro, "já tem roll.yaml"):
            self.adotar()
        outra = self.pasta.parent / "20260815-EM5II-pessoais"
        outra.mkdir()
        (outra / "a.dng").touch()
        (outra / "a.xmp").touch()
        with self.assertRaisesRegex(Erro, "sidecar"):
            self.adotar(outra)
        torta = self.pasta.parent / "2021025-OM1n-kodakdoublex-eleicoes"
        torta.mkdir()
        (torta / "a.jpg").touch()
        with self.assertRaisesRegex(Erro, "fora do padrão"):
            self.adotar(torta)

    def test_varias_pastas_pula_as_que_nao_podem(self):
        from types import SimpleNamespace
        from unittest import mock
        from rolo import adotar
        lixeira = self.cfg.root / "2026" / ".dtrash" / "files"
        lixeira.mkdir(parents=True)
        (lixeira / "x.jpg").touch()
        torta = self.pasta.parent / "2021025-OM1n-kodakdoublex-eleicoes"
        torta.mkdir()
        (torta / "a.jpg").touch()
        with mock.patch.object(adotar, "exif_ler", return_value=self.exif), mock.patch.object(adotar, "aplicar"):
            adotar.executar(self.cfg, self.eq, SimpleNamespace(folder=str(self.cfg.root / "2026"),
                                                               unsent=False, dry_run=False, no_apply=False))
        self.assertTrue(F.caminho(self.pasta).exists())
        self.assertFalse(F.caminho(torta).exists())
        self.assertFalse(F.caminho(lixeira).exists())


class TestCheck(Base):
    def test_pasta_inexistente_e_erro_e_lixeira_ignorada(self):
        import os
        from types import SimpleNamespace
        from unittest import mock
        from rolo.config import Config
        from rolo.manutencao import checar, ignorada
        from rolo.util import Erro
        with mock.patch.dict(os.environ, {"FOTOS_ROOT": str(self.tmp / "acervo")}):
            cfg = Config()
        cfg.root.mkdir(parents=True)
        with self.assertRaisesRegex(Erro, "não encontrada"):
            checar(cfg, self.eq, SimpleNamespace(folder="2025", quick=True))
        self.assertTrue(ignorada(cfg, cfg.root / "2026" / ".dtrash" / "files" / "x.jpg"))
        self.assertTrue(ignorada(cfg, cfg.root / "_inbox" / "x.jpg"))
        self.assertFalse(ignorada(cfg, cfg.root / "2026" / "08-agosto" / "r" / "x.jpg"))


class TestDocumentacao(unittest.TestCase):
    def test_cabecalho_lista_todos_os_campos(self):
        from rolo.campos import FIELDS
        faltando = [c for c in FIELDS + ["share"] if c not in F.CABECALHO]
        self.assertEqual(faltando, [], "campos de FIELDS ausentes do CABECALHO do roll.yaml")


if __name__ == "__main__":
    unittest.main()
