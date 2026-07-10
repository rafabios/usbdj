# USB DJ Formatter

Ferramenta portátil para Windows para preparar pendrives compatíveis com CDJs/XDJs.

## Modos

- **Legado:** FAT32 + MBR, pensado para CDJs antigos.
  - Ate 32 GB: usa ferramentas nativas do Windows.
  - Acima de 32 GB: usa um helper FAT32 grande embutido, como `fat32format.exe`.
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

O helper FAT32 grande ainda precisa ser adicionado em `tools/fat32format.exe` depois de validarmos a licenca escolhida.

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
- rodar o workflow manualmente informando `v0.1.0`.

O asset publicado fica como:

```text
USB-DJ-Formatter-v0.1.0.exe
```
