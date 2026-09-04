"""Bridge passive repository reconnaissance into CYDRA's canonical SystemModel."""
from __future__ import annotations

from .recon import RepositoryRecon
from .system_model import SystemModel
from .system_model_ingestion import project_recon_model


def scan_into_system_model(
    paths: list[str],
    sources: dict[str, str],
    scope_resolver,
) -> SystemModel:
    """Run passive recon, then translate it through the canonical model boundary."""
    recon_model = RepositoryRecon(scope_resolver).scan(paths, sources)
    model = SystemModel()
    project_recon_model(recon_model, model)
    return model
