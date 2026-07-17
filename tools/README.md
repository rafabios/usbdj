# Tools

Coloque aqui o helper FAT32 grande validado para distribuicao.

Nome esperado pelo backend:

```text
tools/fat32format.exe
```

O executavel nao deve ser versionado automaticamente. Antes de embutir no instalador/ZIP final, validar:

- licenca;
- origem/download;
- checksum;
- comportamento em pendrives de teste acima de 32 GiB;
- suporte a execucao silenciosa suficiente para uso pelo app.

Depois da validacao, adicione `tools/fat32format.exe` ao repositorio. O workflow de release falha de proposito se esse arquivo nao existir, para evitar publicar um app sem suporte a FAT32 acima de 32 GiB.
