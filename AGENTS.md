<!-- bmad:context -->
<!-- Verificado em 2026-11-20 contra a árvore de trabalho (repositório ainda sem commits). Gerenciado por bmad-project-context; edições dentro deste bloco são substituídas no refresh. Mantenha o que quiser preservar fora dos marcadores. -->

## rolo

CLI em Python (stdlib + PyYAML) para o fluxo de fotografia analógica e digital: importa scans, grava EXIF com exiftool a partir do `roll.yaml`, gera descrições com Ollama e publica via rclone/Immich. O mesmo código roda no servidor e no PC sobre o acervo compartilhado por NFS; só muda `~/.config/rolo/config.yaml`. O README é a documentação de uso.

## Política

- Nunca edite `../equipment.yaml` nem `../tags.yaml` (no acervo, fora do repo) sem perguntar; proponha a mudança e espere o ok.

## Onde estão as coisas

- Despacho dos subcomandos: `COMANDOS` em `rolo/cli.py`.
- Mesclagem dos quadros e tradução para argumentos do exiftool: `rolo/campos.py`.
- `skill/roll-sheet/SKILL.md` está ligada por symlink em `~/.claude/skills/roll-sheet`: editá-la muda o comportamento do Claude na hora.

## Rodar e verificar

- Testes: `python3 -m unittest discover tests` na raiz do repo. Eles copiam o `equipment.yaml` real de `../`; fora do acervo, falham no setUp.

## Convenções diferentes do padrão

- Identificadores, mensagens e docstrings em português; subcomandos, flags e chaves do `roll.yaml` em inglês.
- Erro esperado: `raise Erro(...)` (`rolo/util.py`), que o `main` mostra sem traceback.
- Grave EXIF só por `exif_gravar` (`rolo/util.py`): uma execução do exiftool, `-overwrite_original`, nunca sidecars `.xmp`.
- Envolva toda escrita numa pasta de rolo em `with trava(pasta):` — PC e servidor rodam o rolo nas mesmas pastas via NFS.
- Nunca grave nota, pick ou etiqueta de cor do digiKam; só leia.
- Prioridade dos metadados: Exif Notes > frames skill/manual > ranges > roll. Equipamentos sempre pelo código de `equipment.yaml`.
- Campo novo ou alterado no `roll.yaml`: atualize `FIELDS` (`rolo/campos.py`), `CABECALHO` (`rolo/ficha.py`), o README e `skill/roll-sheet/SKILL.md`.
- Flag ou subcomando novo: atualize `AJUDA` (`rolo/cli.py`), o README e, se a skill usa, o `SKILL.md`.
- Etapa que conclui trabalho numa pasta registra com `F.registrar(pasta, etapa)`; `rolo/status.py` deduz a etapa disso e do EXIF — altere os dois juntos.

<!-- /bmad:context -->
