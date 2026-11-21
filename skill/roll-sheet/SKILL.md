---
name: roll-sheet
description: Completa o roll.yaml de um rolo de fotos (locais, GPS, lentes, horários, pessoas) a partir do que a usuária descreve na conversa, usando só os equipamentos de equipment.yaml, e roda `rolo apply`. Use sempre que ela falar de locais, horários ou lentes de quadros de um rolo, de EXIF/metadados de scans, de "ficha do rolo" ou do comando rolo. Substitui a geração de scripts .sh do exif-script-fotos.
---

# Ficha do rolo (roll.yaml)

O fluxo de fotos usa o comando `rolo` (código em `$FOTOS_ROOT/_workflow/rolo`). Cada rolo importado tem um `roll.yaml` na pasta. Seu trabalho aqui é **completar esse arquivo** e rodar `rolo apply`. Nada de scripts `.sh`.

## Antes de editar

1. Descubra o acervo: `rolo config` mostra `FOTOS_ROOT` (servidor: `/srv/data/fotos`; PC: `~/fotos`).
2. Leia `roll.yaml` da pasta do rolo e `$FOTOS_ROOT/_workflow/equipment.yaml`.
3. Liste a pasta para confirmar a quantidade de arquivos (`roll.count`).
4. **Ordem dos scans.** Às vezes o lab escaneia do fim para o começo (último scan = quadro 1). Veja `roll`:
   - `scan_order: normal` ou `scan_order: reversed` sem `files_reversed`: os arquivos já estão na ordem do filme (o `rolo import` corrigiu). Siga.
   - `files_reversed: true`: o arquivo `_01` é o **último** quadro do filme. Veja abaixo.
   - Nenhum dos dois (rolo importado antes desta opção): **pergunte** se os scans vieram invertidos antes de escrever qualquer faixa. Depois registre com `rolo sheet PASTA --reversed` ou `--no-reversed` (isso também remapeia os quadros do Exif Notes que já estiverem na ficha).
5. Se o rolo ainda não tiver os quadros do Exif Notes e a usuária tiver o JSON, rode antes:
   `rolo sheet PASTA --exifnotes _inbox/arquivo.json` (acrescente `--reversed` se for o caso da pasta não ter a ordem registrada)

## Regras

- **Equipamentos só da base.** `lens` recebe o código de `equipment.yaml` (`zuiko28`, `zuiko50`, `vivitar80-200`) e precisa ser de uma lente da câmera do rolo. Se ela citar um equipamento fora da base, pare e pergunte se deve cadastrá-lo; não invente códigos.
- **Nunca altere nem contradiga `frames` com `source: exifnotes`.** Eles têm prioridade máxima no `rolo apply` mesmo. Se o que ela disser conflitar com um deles, aponte o conflito no resumo.
- **Escreva em `ranges`** para faixas de quadros (`frames: 1-10` ou `1-3,7`) com `source: skill`. Use `frames` com `source: skill` para um quadro só.
- **Localização**: `lat`/`lon` em graus decimais com sinal (Brasil: ambos negativos), `location` (ponto específico ou endereço), `sublocation` (bairro), `city`, `state` (sigla), `country` (em inglês, ex.: `Brazil`). Use coordenadas do ponto citado, não do centro da cidade; pesquise na web quando não tiver certeza e diga qual interpretação usou. Sem local conhecido, **não invente GPS**: deixe sem e pergunte.
- **Números de quadro no `roll.yaml` são sempre números de arquivo** (`_01`, `_02`…). Com `files_reversed: true`, converta o que ela disser na ordem do filme ("as primeiras 10 fotos") para arquivos: quadro do filme `q` = arquivo `count + 1 - q` (ex.: 36 exposições, quadros 1-10 → `frames: 27-36`). Se não der para saber se ela fala de quadro do filme ou de arquivo, pergunte. O `rolo apply` já ordena os horários de `start`/`end` do maior arquivo para o menor e grava o quadro do filme em `ImageNumber`.
- **Horários**: em vez de datas por quadro, use `start`/`end` na faixa ("2026-11-15 14:00"). O `rolo` distribui horários crescentes. Atenção à virada do dia ("2h da manhã" depois de uma noite = dia seguinte).
- **Exposição**: `aperture` ("8"), `shutter` ("1/125"), `flash` (true/false), `focal_length` (zoom). Só preencha o que ela informar; não use exposições "padrão".
- **Álbum por sessão**: proponha um `album` por sessão (um evento, passeio ou dia) em cada faixa, no formato `<ano> <nome curto>` (ex.: `album: 2026 Halloween`, `album: 2026 Eleições`), e diga quais propôs no resumo. O `rolo albums` acrescenta o prefixo sozinho (Analog/Vintage/Photography); não escreva o prefixo. Sem `album`, o álbum vira `<ano> <título do rolo>`. Só pergunte sobre `personal: true` quando houver sinal de foto de família (parentes, aniversário, casa, crianças); nesse caso, confirme antes de marcar. Em rolo digital com lente manual adaptada, ponha `lens` na faixa (o álbum vira `Vintage - …`).
- **Pessoas**: `people: [Nome]`. `description` é texto livre curto; deixe vazio se ela não disser nada. O `rolo ai` preenche depois.
- Mantenha o cabeçalho de comentários e a seção `roll` intactos (só altere `roll.offset` se o lab numerou diferente do Exif Notes).

## Depois de editar

1. `rolo apply PASTA --dry-run --show 2` para conferir.
2. `rolo apply PASTA`.
3. Responda com um resumo curto: uma tabela por faixa (quadros, local, horário, lente/exposição), depois **O que foi assumido** e **O que precisa de confirmação** (locais sem GPS, conflitos com o Exif Notes, coordenadas aproximadas).

Correções chegam uma de cada vez: edite o `roll.yaml`, rode `rolo apply` de novo e diga só o que mudou.
