# Local models

This directory holds the model files the local services load. **Model files
are large and are not committed** — `.gitignore` keeps everything here except
this README. The dev launcher (`scripts/dev.sh`) looks here by default.

## What goes here

| File (default name) | Used by | Backend setting it satisfies |
| --- | --- | --- |
| `gemma-4-e4b.gguf` | `llama-server` (LLM) | `llm_model` alias `gemma-4-e4b` |
| `ggml-base.bin`    | `whisper-server` (STT) | `stt_model` alias `whisper-base` |

> **Names vs. paths.** `apps/backend/config.py` only stores model *names*
> (`llm_model`, `stt_model`) — the strings the backend sends to the servers. It
> never stores a file path. The *path* is a launcher concern: `scripts/dev.sh`
> passes it to each server via `-m`. Override the defaults with
> `WHETSTONE_GEMMA_GGUF` and `WHETSTONE_WHISPER_GGML`.

## Getting the models

See the **README → "Getting the models"** section for the full, copy-pasteable
download steps (Hugging Face for the Gemma GGUF, whisper.cpp's
`download-ggml-model.sh` for the Whisper model), and how to build
`llama-server` / `whisper-server` so they're on your `PATH`.
