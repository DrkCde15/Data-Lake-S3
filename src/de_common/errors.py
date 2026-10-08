"""Pipeline error hierarchy. Fail fast, never swallow."""


class DataPipelineError(Exception):
    """Base error for all pipeline failures."""


class ConfigError(DataPipelineError):
    """Invalid or missing configuration (env vars, arguments)."""


class ValidationError(DataPipelineError):
    """Input data failed validation (schema, types, ranges)."""


class InfraError(DataPipelineError):
    """AWS/local infra call failed after retries."""
