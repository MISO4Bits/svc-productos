from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración por variables de entorno (prefijo ``PRODUCTOS_``)."""

    model_config = SettingsConfigDict(env_prefix="PRODUCTOS_", env_file=".env", extra="ignore")

    service_name: str = "svc-productos"
    environment: str = "local"

    # Persistencia: "sqlite" (local / dev) | "memory" (pruebas)
    # Cuando se adopte Cloud Spanner (DI-009) se añade un adaptador con el mismo puerto.
    repository_backend: str = "sqlite"
    database_path: str = "./svc_productos.db"

    # Carga inicial de documentos legales al arrancar (idempotente: solo inserta
    # las versiones que todavía no existen, nunca modifica una ya publicada).
    seed_enabled: bool = True
    seed_autor: str = "seed-inicial"

    # Observabilidad (DI-008): OTLP/gRPC hacia Grafana Alloy dentro del
    # cluster. Deshabilitado por defecto — en local/tests no hay receptor
    # escuchando; se habilita vía PRODUCTOS_OTEL_ENABLED=true en el manifiesto
    # de despliegue.
    otel_enabled: bool = False
    otel_exporter_endpoint: str = (
        "k8s-monitoring-alloy-receiver.observability.svc.cluster.local:4317"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
