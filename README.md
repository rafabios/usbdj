# USB DJ Formatter

Ferramenta portátil para Windows para preparar pendrives compatíveis com CDJs/XDJs.

## Modos

- **Legado:** FAT32 + MBR, pensado para CDJs antigos.
  - Ate 32 GB: usa ferramentas nativas do Windows.
  - Acima de 32 GB: usa o formatador FAT32 interno do app.
  - Exemplos: CDJ-350, CDJ-850, CDJ-900, CDJ-2000, XDJ-AERO, XDJ-R1, XDJ-RX.
- **Novo:** exFAT + MBR, pensado para CDJs/XDJs recentes.
  - Exemplos: CDJ-3000, CDJ-3000X, XDJ-RX2, XDJ-RR, XDJ-XZ, XDJ-RX3, OPUS-QUAD, OMNIS-DUO, XDJ-AZ.

## Estado atual

Este repositorio comeca com um MVP seguro:

- regra de decisao do backend;
- listagem de discos removiveis no Windows;
- CLI com modo de simulacao;
- GUI simples;
- painel avancado escondido com formato, particao, cluster e label;
- backend com comandos Windows isolados;
- pedido de permissao do Windows para execucao real;
- confirmacao digitada antes de apagar;
- log de execucao em `logs/`;
- validacao final de filesystem, label e estilo de particao;
- testes unitarios do planejador.

FAT32 acima de 32 GiB e formatado pelo backend interno do app, sem depender de `fat32format.exe` ou outro binario externo.

## Uso em desenvolvimento

```powershell
python -m usbdj.cli list
python -m usbdj.cli plan --mode legacy --size-gb 64
python -m usbdj.cli format --disk 2 --mode legacy
python -m usbdj.gui
```

O comando `format` roda em simulacao por padrao. Para executar de verdade, precisa:

```powershell
python -m usbdj.cli format --disk 2 --mode legacy --execute --confirm FORMATAR
```

Use apenas em uma maquina de teste com um pendrive descartavel conectado.

Ao rodar pelo Python, talvez seja necessario abrir o PowerShell aceitando a permissao do Windows. No executavel final, essa permissao sera pedida automaticamente.

## Build do executavel

Com PyInstaller instalado:

```powershell
pyinstaller packaging/usbdj.spec
```

O executavel final ficara em `dist/USB-DJ-Formatter.exe`.

## Release no GitHub

O workflow `.github/workflows/release.yml` gera o binario em Windows e publica uma Release.

Opcoes:

- criar e enviar uma tag `v*`, por exemplo `v0.1.0`;
- rodar o workflow manualmente. Se a versao ficar vazia, ele usa `version` do `pyproject.toml`;
- rodar o workflow manualmente informando o campo `tag` como `v0.1.0` ou `0.1.0`.

Ao rodar manualmente, o workflow cria a tag no commit atual e publica a Release.

Os assets publicados ficam como:

```text
USB-DJ-Formatter-v0.1.1.exe
USB-DJ-Formatter-latest.exe
```

A pagina usa o link estavel `releases/latest/download/USB-DJ-Formatter-latest.exe`, entao nao precisa ser atualizada a cada versao.
