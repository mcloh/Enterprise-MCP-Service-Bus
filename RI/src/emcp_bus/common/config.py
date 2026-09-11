"""YAML -> Pydantic configuration loading with environment-variable interpolation.

Every declarative config type in the RI (client profiles, capability manifests,
policies, ...) is loaded through :func:`load_yaml_model`, so secrets never live
as literal values in a committed YAML file (see docs/RI-PLANNING.md, EP-00-T05):
a value written as ``${VAR_NAME}`` or ``${VAR_NAME:-default}`` is resolved from
the environment at load time, and a value that still looks like an unresolved
placeholder after interpolation is treated as a configuration error.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)

_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-(.*?))?\}")


class ConfigError(Exception):
    """Raised when a YAML config file fails to parse or to validate against its model."""


def _interpolate_env_vars(raw_text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        var_name, _, default = match.groups()
        if var_name in os.environ:
            return os.environ[var_name]
        if default is not None:
            return default
        raise ConfigError(
            f"Environment variable '{var_name}' referenced in config is not set "
            "and no default was provided (use ${VAR:-default} for optional values)."
        )

    return _ENV_VAR_PATTERN.sub(_replace, raw_text)


def load_yaml_model[ModelT: BaseModel](path: str | Path, model: type[ModelT]) -> ModelT:
    """Load a single YAML document at ``path`` and validate it against ``model``.

    Raises :class:`ConfigError` on a missing file, invalid YAML, or a document
    that fails Pydantic validation -- callers should treat this as a fatal
    startup error (fail closed), never as a recoverable condition.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ConfigError(f"Config file not found: {file_path}")

    raw_text = file_path.read_text(encoding="utf-8")
    interpolated = _interpolate_env_vars(raw_text)

    try:
        document = yaml.safe_load(interpolated)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {file_path}: {exc}") from exc

    if document is None:
        document = {}

    try:
        return model.model_validate(document)
    except ValidationError as exc:
        raise ConfigError(f"Config validation failed for {file_path}:\n{exc}") from exc


def load_yaml_models[ModelT: BaseModel](
    directory: str | Path, model: type[ModelT], pattern: str = "*.yaml"
) -> list[ModelT]:
    """Load and validate every file matching ``pattern`` under ``directory``.

    Files are returned sorted by filename for deterministic ordering (config
    load order must never be a source of non-determinism in the PEP/PDP path).
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise ConfigError(f"Config directory not found: {dir_path}")

    return [load_yaml_model(file_path, model) for file_path in sorted(dir_path.glob(pattern))]
