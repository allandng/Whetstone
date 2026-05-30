"""Standalone model-quality evaluation harness (SRS §9.3 spike).

This package is NOT part of the application and NOT part of the default test
run: it lives outside the ``test_*.py`` naming convention pytest collects, and
every measurement needs a live ``llama-server`` (see ``model_eval/README.md``).

Run it manually against a running server::

    cd apps/backend
    python -m model_eval.run --model-label "gemma-4-e4b" --only all

The grading logic is pure and can be validated offline (no server) with::

    python -m model_eval.run --self-check
"""
