# ADR-0004: LLMProvider abstraction, Ollama default, small models chosen by evals

**Status:** Accepted — 2026-10-29

## Context
The game is installed with `uvx` on macOS, Linux and Windows, and targets machines with 8 GB RAM and CPU only. Embedding `llama-cpp-python` often means compiling from source on user machines. Ollama has one-click installers on all three platforms and supports output forced to a JSON Schema.

## Decision
- All model access goes through an `LLMProvider` interface. Backends in the MVP:
  - **Ollama** (the default)
  - **OpenAI-compatible** endpoints (LM Studio, llama-server, vLLM)
  - **Fake** (scripted, for tests)
- The model target is **3–4B parameters on CPU**, and development runs against the weakest supported model. A larger "quality" model can be set in the config.
- **The model is chosen by evals:** about 30 cases each for classify, narrate and NPC voice, compared across candidates (starting with `granite4.1:3b` and `qwen3.5:2b`). The config can assign a different model to each task.
- The model's licence must allow redistribution or automatic download.
- Narration **streams**. Budget: first text in under 2 s, a full turn in under 10 s; narration is capped at 2–4 sentences.
- An embedded backend can come later, behind the same interface.

## Consequences
- \+ No native build problems for players, and no lock-in to Ollama.
- \+ Evals make model upgrades a measured decision.
- − Players must install Ollama separately. M7 handles detecting it and pulling the model on first run.
