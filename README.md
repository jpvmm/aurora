# Aurora CLI

Aurora e um assistente local-first para uso via terminal.

## Instalacao global

Opcao recomendada com `uv tool`:

```bash
uv tool install .
```

Opcao alternativa com `pipx`:

```bash
pipx install .
```

## Resolucao de PATH

Se o comando `aurora` nao for encontrado apos a instalacao:

```bash
uv tool update-shell
pipx ensurepath
```
