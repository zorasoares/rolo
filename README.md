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
rolo apply PASTA          → grava roll.yaml nos arquivos (sem .xmp)
rolo ai PASTA             → título/descrição/keywords por IA local onde falta, exceto recusadas (tag ai:generated)
  digiKam: revisar ai:generated
rolo portfolio PASTA      → todas menos recusadas, 2048px com EXIF completo → Immich + Google Photos + reindex PhotoPrism
rolo backup               → rclone sync do acervo (cron noturno no servidor)
rolo check [PASTA]        → pastas/arquivos/EXIF fora do padrão
rolo status [PASTA]       → em que etapa cada rolo está e qual o próximo comando
```

`rolo status` deduz a etapa sozinho, sem marcação manual: roll.yaml, EXIF (pick, etiqueta, GPS, `ai:generated`), `_outbox/` e `PASTA/.rolo-history.yaml`, onde `rolo apply`, `rolo print` e `rolo portfolio` anotam quando terminaram e quais fotos foram enviadas. O apply fica pendente quando o EXIF (GPS, data, lente, cidade, número do quadro) não bate com o roll.yaml. Sem PASTA (e fora de uma pasta de rolo), mostra só os rolos com algo pendente e as pastas em `_inbox/`.

Arquivos:

| Arquivo | O que é |
|---|---|
| `$FOTOS_ROOT/_workflow/equipment.yaml` | base de câmeras, lentes e filmes (única fonte de nomes) |
| `$FOTOS_ROOT/_workflow/tags.yaml` | vocabulário de tags do `rolo ai` (a IA só escolhe daqui) |
| `$FOTOS_ROOT/_workflow/tags-suggested.txt` | termos que a IA quis marcar fora do vocabulário, para promover ao `tags.yaml` |
| `PASTA/roll.yaml` | ficha do rolo: dados do rolo, faixas (skill/manual) e quadros (Exif Notes) |
| `$FOTOS_ROOT/_inbox/` | downloads do lab e JSON do Exif Notes |
| `$FOTOS_ROOT/_outbox/` | JPGs gerados (`print/`, `portfolio/`) |

**Scans em ordem invertida** (o lab escaneou do fim para o começo, último scan = quadro 1): o `rolo import` pergunta (ou `--reversed`) e renomeia na ordem do filme; a ficha registra `scan_order: reversed`. Para uma pasta já importada sem essa correção, `rolo sheet PASTA --reversed` grava `files_reversed: true` sem renomear nada: os quadros do Exif Notes são remapeados (arquivo = total + 1 − quadro), os horários das faixas correm do último arquivo para o primeiro e o `ImageNumber` recebe o quadro do filme. Se a ficha não disser a ordem, o `rolo sheet` pergunta.

**Tags do `rolo ai`**: só de `tags.yaml` (gênero, técnica, assunto forte, hora e luz, plano e, em filme, defeitos), de 0 a 8 por foto, em inglês e gravadas como `grupo:termo` (`light:blue-hour`, `framing:close-up`), no padrão de `camera:` e `film:`. Lugar, evento e pessoas já vão em outros campos e nunca viram tag; detalhes como roupas e objetos ficam na descrição, que continua buscável. `rolo ai PASTA --redo` refaz as fotos que ainda têm `ai:generated` e **troca** as keywords nos quatro campos que o digiKam espelha (Subject, TagsList, HierarchicalSubject, IPTC Keywords): apaga só as com prefixo de um grupo do `tags.yaml`, então suas tags simples, `projeto/…`, `People/…`, `camera:`, `film:` e `filter:` ficam. Exceção: fotos da versão antiga do `rolo ai` (sem nenhuma tag de grupo) perdem também as tags simples, menos as do roll.yaml. Depois, no digiKam: Item → Reread Metadata From Files.

Seleção pelo digiKam:

| Comando | O que entra |
|---|---|
| `rolo print` | etiqueta de cor `conventions.print_label` (padrão: verde) |
| `rolo portfolio` | todas menos as com pick **recusada**; com `portfolio_pick: accepted` em `conventions`, só as **aceitas** |
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

Google Photos: a API só deixa o rclone enviar para álbuns criados por ele mesmo. Deixe o `rolo portfolio` criar o "Portfólio" na primeira vez.

### digiKam (PC)

- Configurações → Metadados → **Comportamento**: marque gravar nota, etiquetas (cor/escolha), tags e legendas **nos arquivos**. **Desmarque** "gravar em arquivos sidecar". Marque "gravar metadados em arquivos RAW" (necessário para os DNG).
- Configurações → Editor → **Versionamento**: ative. O original nunca é alterado e a edição vira `nome_v1.jpg`. `rolo print` e `rolo portfolio` usam a versão mais recente.

### RapidRAW (PC, edição)

- Só edição: nota, pick e etiqueta continuam no digiKam, no arquivo original. As do RapidRAW ficam no `.rrdata` e não chegam ao export de forma confiável.
- Exportar: JPG, na própria pasta do rolo, com o nome do original + `_edited` (ex.: `..._02_edited.jpg`). O export copia os metadados do original.
- `rolo print` e `rolo portfolio` usam `NOME_edited.jpg` quando existe; senão a maior `NOME_vN` do digiKam; senão o original.
- Coleções: adicione `~/fotos/2026` (e anos seguintes) como coleção de **rede**. O banco fica no disco local do PC.

## Testes

```bash
cd ~/fotos/_workflow/rolo && python3 -m unittest discover tests
```
