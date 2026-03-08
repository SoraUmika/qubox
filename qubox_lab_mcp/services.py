"""Service container wiring adapters and policies together."""
from __future__ import annotations

from dataclasses import dataclass

from .adapters.decomposition_adapter import DecompositionAdapter
from .adapters.filesystem_adapter import FilesystemAdapter
from .adapters.json_adapter import JsonAdapter
from .adapters.notebook_adapter import NotebookAdapter
from .adapters.python_index_adapter import PythonIndexAdapter
from .adapters.run_adapter import RunAdapter
from .config import ServerConfig
from .policies.path_policy import PathPolicy
from .policies.safety_policy import SafetyPolicy


@dataclass(slots=True)
class ServiceContainer:
    config: ServerConfig
    path_policy: PathPolicy
    safety_policy: SafetyPolicy
    filesystem: FilesystemAdapter
    notebook: NotebookAdapter
    python_index: PythonIndexAdapter
    json: JsonAdapter
    decomposition: DecompositionAdapter
    run: RunAdapter


def build_services(config: ServerConfig) -> ServiceContainer:
    path_policy = PathPolicy(config)
    safety_policy = SafetyPolicy(config)
    filesystem = FilesystemAdapter(config, path_policy, safety_policy)
    notebook = NotebookAdapter(path_policy, safety_policy)
    json_adapter = JsonAdapter(path_policy, safety_policy)
    python_index = PythonIndexAdapter(filesystem)
    decomposition = DecompositionAdapter(json_adapter)
    run = RunAdapter(config, path_policy)
    return ServiceContainer(
        config=config,
        path_policy=path_policy,
        safety_policy=safety_policy,
        filesystem=filesystem,
        notebook=notebook,
        python_index=python_index,
        json=json_adapter,
        decomposition=decomposition,
        run=run,
    )
