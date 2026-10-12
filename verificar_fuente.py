# -*- coding: utf-8 -*-
"""Detecta cambios en el PDF oficial de la LFPA mediante SHA-256.

No interpreta el PDF, no cambia reglas ni crea dias inhabiles automaticamente.
Su primera ejecucion crea una huella de referencia; posteriores ejecuciones comparan.
Solo biblioteca estandar de Python.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

from lfpa import FUENTE_LFPA


def verificar(archivo_estado: Path, url: str = FUENTE_LFPA["url"]) -> int:
    peticion = Request(url, headers={"User-Agent": "Motor-LFPA-CRT/1.0 (revision documental)"})
    max_bytes = 25 * 1024 * 1024
    try:
        with urlopen(peticion, timeout=20) as respuesta:
            pdf = respuesta.read(max_bytes + 1)
        if not pdf.startswith(b"%PDF-") or len(pdf) > max_bytes:
            print("Error: el servidor no devolvio un PDF valido de tamano admisible", file=sys.stderr)
            return 2
        digest = hashlib.sha256(pdf).hexdigest()
        ahora = datetime.now(timezone.utc).isoformat()
        if archivo_estado.exists():
            estado = json.loads(archivo_estado.read_text(encoding="utf-8"))
            anterior = estado.get("sha256_pdf")
            if anterior != digest:
                print("ALERTA: el archivo PDF oficial ha cambiado respecto al registrado.")
                print("Revisar manualmente el articulo 28 y aprobar posibles ajustes de reglas.")
                print("La huella guardada NO se sustituyo automaticamente.")
                print(f"Documento: {url}")
                return 1
            estado["ultima_comprobacion_utc"] = ahora
            archivo_estado.write_text(json.dumps(estado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Sin cambios detectados en el PDF desde la huella registrada. {ahora}")
            return 0
        else:
            estado = {"fuente": url, "sha256_pdf": digest, "registrado_utc": ahora,
                      "ultima_comprobacion_utc": ahora}
            archivo_estado.parent.mkdir(parents=True, exist_ok=True)
            archivo_estado.write_text(json.dumps(estado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print("Primera revision: se guardo la huella del PDF oficial.")
            print("El contenido y las reglas deben ser validados manualmente; repetir para detectar cambios.")
            return 0
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print(f"No se pudo comprobar la fuente: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Comprueba cambios del PDF LFPA oficial sin pago ni API key")
    parser.add_argument("--estado", default="huella_fuente_lfpa.json", help="Ruta del registro SHA-256")
    args = parser.parse_args()
    sys.exit(verificar(Path(args.estado)))
