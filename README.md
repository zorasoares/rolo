# rolo

Fluxo de fotografia (filme e digital) num comando só. O mesmo código roda no **servidor** e no **PC**; muda só `~/.config/rolo/config.yaml`.

```
rolo download LINK        → _inbox/
rolo import               → menu (câmera/filme/lente de equipment.yaml, ordem dos scans) → AAAA/MM-mes/AAAAMMDD-CAM-filme-titulo/
  digiKam: classificar      nota, pick (recusadas ficam de fora), etiqueta verde (gráfica)
  RapidRAW: editar          exporta NOME_edited.jpg na pasta do rolo (classificação só no digiKam)
rolo print PASTA          → verdes em JPG → Drive da gráfica
rolo sheet PASTA --exifnotes _inbox/x.json   → roll.yaml
  Claude + skill roll-sheet completa locais/lentes no roll.yaml
rolo apply PASTA          → grava roll.yaml nos arquivos (sem .xmp) + reindex PhotoPrism
rolo albums PASTA         → não recusadas ainda não enviadas, JPG em resolução cheia, um álbum por sessão → Immich + Google Photos
rolo ai PASTA             → (opcional) título/descrição/keywords por IA local onde falta, exceto recusadas (tag ai:generated)
  digiKam: revisar ai:generated
rolo backup               → rclone sync do acervo (cron noturno no servidor)
rolo check [PASTA]        → pastas/arquivos/EXIF fora do padrão
rolo status [PASTA]       → em que etapa cada rolo está e qual o próximo comando
```

`rolo status` deduz a etapa sozinho, sem marcação manual: roll.yaml, EXIF (pick, etiqueta, GPS, `ai:generated`), `_outbox/` e `PASTA/.rolo-history.yaml`, onde `rolo apply`, `rolo print` e `rolo albums` anotam quando terminaram e quais fotos (e álbuns) foram enviados. O apply fica pendente quando o EXIF (GPS, data, lente, cidade, número do quadro) não bate com o roll.yaml. Sem PASTA (e fora de uma pasta de rolo), mostra só os rolos com algo pendente e as pastas em `_inbox/`.

Arquivos:

| Arquivo | O que é |
|---|---|
| `$FOTOS_ROOT/_workflow/equipment.yaml` | base de câmeras, lentes e filmes (única fonte de nomes) |
| `$FOTOS_ROOT/_workflow/tags.yaml` | vocabulário de tags do `rolo ai` (a IA só escolhe daqui) |
| `$FOTOS_ROOT/_workflow/tags-suggested.txt` | termos que a IA quis marcar fora do vocabulário, para promover ao `tags.yaml` |
| `PASTA/roll.yaml` | ficha do rolo: dados do rolo, faixas (skill/manual) e quadros (Exif Notes) |
| `$FOTOS_ROOT/_inbox/` | downloads do lab e JSON do Exif Notes |
| `$FOTOS_ROOT/_outbox/` | JPGs gerados (`print/`, `albuns/<álbum>/`; `albuns/_staging/` durante o envio e no `--dry-run`) |

**Scans em ordem invertida** (o lab escaneou do fim para o começo, último scan = quadro 1): o `rolo import` pergunta (ou `--reversed`) e renomeia na ordem do filme; a ficha registra `scan_order: reversed`. Para uma pasta já importada sem essa correção, `rolo sheet PASTA --reversed` grava `files_reversed: true` sem renomear nada: os quadros do Exif Notes são remapeados (arquivo = total + 1 − quadro), os horários das faixas correm do último arquivo para o primeiro e o `ImageNumber` recebe o quadro do filme. Se a ficha não disser a ordem, o `rolo sheet` pergunta.

**Tags do `rolo ai`**: só de `tags.yaml` (gênero, técnica, assunto forte, hora e luz, plano e, em filme, defeitos), de 0 a 8 por foto, em inglês e gravadas como `grupo:termo` (`light:blue-hour`, `framing:close-up`), no padrão de `camera:` e `film:`. Lugar, evento e pessoas já vão em outros campos e nunca viram tag; detalhes como roupas e objetos ficam na descrição, que continua buscável. `rolo ai PASTA --redo` refaz as fotos que ainda têm `ai:generated` e **troca** as keywords nos quatro campos que o digiKam espelha (Subject, TagsList, HierarchicalSubject, IPTC Keywords): apaga só as com prefixo de um grupo do `tags.yaml`, então suas tags simples, `projeto/…`, `People/…`, `camera:`, `film:` e `filter:` ficam. Exceção: fotos da versão antiga do `rolo ai` (sem nenhuma tag de grupo) perdem também as tags simples, menos as do roll.yaml. Depois, no digiKam: Item → Reread Metadata From Files.

**Álbuns por sessão** (`rolo albums PASTA`, antigo `rolo portfolio`, que continua como apelido): cada faixa ou quadro do `roll.yaml` pode ter `album` (a sessão, ex.: `album: 2026 Halloween`) e `personal: true` (foto de família). O nome do álbum é calculado por foto:

| Foto | Álbum |
|---|---|
| filme (com ou sem `personal`) | `Analog - <sessão>` |
| digital com lente marcada `vintage: true` no `equipment.yaml` (via `lens` na faixa/quadro) | `Vintage - <sessão>` |
| outro digital | `Photography - <sessão>` |
| digital com `personal: true` | `<sessão>` (sem prefixo) |

Sem `album`, a sessão é `<ano do rolo> <título do rolo>` (ex.: `Analog - 2026 paulista`). `album` também vai no JPG como `XMP-iptcExt:Event`; `personal` vira a keyword `personal`. Lente vintage em câmera digital: a lente precisa listar a câmera em `cameras:` no `equipment.yaml` (senão o `rolo apply` dá erro) e o apply grava as tags de lente, que a câmera não registra.

O comando exporta para `_outbox/albuns/_staging/`, confere o EXIF, envia cada álbum ao Immich (`immich upload --album-name`, se `ROLO_IMMICH` não estiver vazio) e ao Google Photos (`rclone copy … <ROLO_GPHOTOS>album/<álbum>`, se `ROLO_GPHOTOS` não estiver vazio) e move os JPGs para `_outbox/albuns/<álbum>/`. **Cada foto é enviada uma vez só**: o `.rolo-history.yaml` guarda quais já foram (inclusive as do antigo `rolo portfolio`) e uma nova execução só envia as aceitas depois; sem fotos novas, diz "nada novo". Nada é apagado nem reenviado no Immich ou no Google. Foto ainda com `ai:generated` sai com aviso, mas sem o título, a descrição e as tags de grupo da IA (título/descrição do `roll.yaml` ficam); câmera, filme, lente, data e GPS vão sempre. Se o `rolo apply` rodar depois do envio, o `rolo status` avisa "dados antigos no Immich/Google", sem pedir reenvio. `--dry-run` deixa os JPGs no staging sem enviar nem registrar; `--force` exporta mesmo com EXIF incompleto. Rolo contratado: `share: false` na seção `roll` → só exporta para `_outbox/albuns/`, sem enviar (e registra como entregue). Configuração: `ROLO_GPHOTOS` (remoto base, ex. `gphotos:`) e `ROLO_IMMICH` (`on`; vazio, `off`, `false`, `no` ou `0` desliga — vale também para `share`) substituem `ROLO_RCLONE_GPHOTOS` e `ROLO_IMMICH_ALBUM`; as chaves antigas geram um aviso, e uma antiga vazia desliga a nova se ela não estiver definida. Sem nenhum destino ligado (e `share` ligado), os JPGs são exportados mas nada é registrado: ao ligar um destino, a próxima execução envia essas fotos.

Seleção pelo digiKam:

| Comando | O que entra |
|---|---|
| `rolo print` | etiqueta de cor `conventions.print_label` (padrão: verde) |
| `rolo albums` | todas menos as com pick **recusada**; com `portfolio_pick: accepted` em `conventions`, só as **aceitas** |
| `rolo ai` | todas menos as recusadas (e só onde falta descrição) |

Prioridade dos metadados: **Exif Notes > roll.yaml (skill/manual) > base do rolo**. A nota e a etiqueta do digiKam nunca são tocadas.

## Instalação

### Servidor (Debian)

```bash
sudo apt install python3-yaml libimage-exiftool-perl rclone libvips-tools nfs-kernel-server
ln -s /srv/data/fotos/_workflow/rolo/bin/rolo ~/.local/bin/rolo
mkdir -p ~/.config/rolo && cp /srv/data/fotos/_workflow/rolo/config.example.yaml ~/.config/rolo/config.yaml
rclone config     # remoto "drive" (Google Drive)
```

NFS: `/etc/exports` libera o PC na LAN e a rede Tailscale, sempre gravando como o seu usuário (aqui, uid 1000):
```
/srv/data/fotos IP-DO-PC(rw,sync,no_subtree_check,all_squash,anonuid=1000,anongid=1000) 100.64.0.0/10(rw,sync,no_subtree_check,all_squash,anonuid=1000,anongid=1000)
```
Depois de editar: `sudo exportfs -ra`. Reserve um IP fixo para o PC no DHCP do roteador.

Backup noturno (`crontab -e`):
```
30 3 * * * $HOME/.local/bin/rolo backup >> $HOME/.cache/rolo-backup.log 2>&1
```

PhotoPrism: monte `/srv/data/fotos` como `originals` em modo somente leitura (`PHOTOPRISM_READONLY: "true"`). Crie `/srv/data/fotos/.ppignore` com a linha `_*` para ele ignorar `_inbox`, `_outbox` e `_workflow`.

### PC (Linux)

```bash
sudo apt install python3-yaml libimage-exiftool-perl rclone libvips-tools nfs-common digikam darktable
# dnglab (ORF → DNG): baixe o .deb em https://github.com/dnglab/dnglab/releases e instale com apt
curl -fsSL https://ollama.com/install.sh | sh && ollama pull qwen2.5vl:7b
sudo npm i -g @immich/cli && immich login https://SEU-IMMICH/api SUA-API-KEY

mkdir -p ~/fotos
# IP-DO-SERVIDOR: o da LAN em casa; fora de casa, o do Tailscale
echo "IP-DO-SERVIDOR:/srv/data/fotos  $HOME/fotos  nfs  defaults,_netdev,noatime,nofail,x-systemd.automount  0 0" | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo mount ~/fotos

ln -s ~/fotos/_workflow/rolo/bin/rolo ~/.local/bin/rolo
mkdir -p ~/.config/rolo && cp ~/fotos/_workflow/rolo/config.example.yaml ~/.config/rolo/config.yaml
rclone config     # remotos "drive" e "gphotos" (Google Photos)
mkdir -p ~/.claude/skills && ln -s ~/fotos/_workflow/rolo/skill/roll-sheet ~/.claude/skills/roll-sheet
rolo config       # confere
```

Google Photos: a API só deixa o rclone enviar para álbuns criados por ele mesmo. Deixe o `rolo albums` criar cada álbum (não crie à mão no app).

### digiKam (PC)

- Configurações → Metadados → **Comportamento**: marque gravar nota, etiquetas (cor/escolha), tags e legendas **nos arquivos**. **Desmarque** "gravar em arquivos sidecar". Marque "gravar metadados em arquivos RAW" (necessário para os DNG).
- Configurações → Editor → **Versionamento**: ative. O original nunca é alterado e a edição vira `nome_v1.jpg`. `rolo print` e `rolo albums` usam a versão mais recente.

### RapidRAW (PC, edição)

- Só edição: nota, pick e etiqueta continuam no digiKam, no arquivo original. As do RapidRAW ficam no `.rrdata` e não chegam ao export de forma confiável.
- Exportar: JPG, na própria pasta do rolo, com o nome do original + `_edited` (ex.: `..._02_edited.jpg`). O export copia os metadados do original.
- `rolo print` e `rolo albums` usam `NOME_edited.jpg` quando existe; senão a maior `NOME_vN` do digiKam; senão o original.
- Coleções: adicione `~/fotos/2026` (e anos seguintes) como coleção de **rede**. O banco fica no disco local do PC.

## Testes

```bash
cd ~/fotos/_workflow/rolo && python3 -m unittest discover tests
```
