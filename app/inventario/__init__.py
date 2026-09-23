"""Inventario propio → `PropertyContextV0` (PLAN04-1.4).

Aquí vive el **adaptador local**: la traducción de una fila del catastro propio al contrato
congelado en F1. Nada más. No hay Partner Layer, ni multi-tenant, ni auth por proveedor, ni
ingesta de terceros — todo eso es F5, y el contrato ya lo dice de frente: *«Que el contrato
lo tenga NO construye Partner Layer. Solo deja de hacerla imposible.»*

POR QUÉ ESTE PAQUETE SE LLAMA `inventario` Y NO `property`: `app.property` funcionaría, pero
un módulo llamado `property` dentro de un paquete que usa el decorador `property` es una
trampa gratuita. `inventario` es además la palabra que el Plan 04 usa para esta costura
(«adaptador de inventario»).

**Lo que hay aquí NO es un contrato.** Los contratos viven en `app/contracts/` y están
congelados; esto es una capa interna que los produce y que se puede cambiar sin versionar.
"""

from app.inventario.adaptador_local import (
    ContextoDeLectura,
    ensamblar_property_context,
    leer_activos_locales,
)

__all__ = [
    "ContextoDeLectura",
    "ensamblar_property_context",
    "leer_activos_locales",
]
