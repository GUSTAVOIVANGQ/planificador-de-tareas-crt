# -*- coding: utf-8 -*-
"""Motor de dias inhabiles de la Ley Federal de Procedimiento Administrativo (Mexico).

Fuente: Camara de Diputados, LFPA, articulo 28:
https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPA.pdf

Requiere Python 3.10+. No necesita bibliotecas externas ni internet para los calculos.
Este modulo calcula el CALENDARIO BASE LFPA, no los descansos laborales de la CRT.
No agrega suspensiones de plazos como si fueran dias de descanso.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

FUENTE_LFPA: dict[str, str] = {
    "ley": "Ley Federal de Procedimiento Administrativo",
    "articulo": "28",
    "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPA.pdf",
    "revision_indicada_en_pdf": "DOF 14-11-2025",
    "alcance": (
        "Calendario base de dias inhabiles para actuaciones y plazos administrativos "
        "cuando aplica la LFPA; no equivale a dias de descanso del personal de la CRT."
    ),
}

# Las fechas son literales segun el art. 28: NO se recorren a lunes.
FERIADOS_FIJOS: dict[str, str] = {
    "01-01": "1 de enero (Año Nuevo)",
    "02-05": "5 de febrero",
    "03-21": "21 de marzo",
    "05-01": "1 de mayo (Día del Trabajo)",
    "05-05": "5 de mayo",
    "09-01": "1 de septiembre",
    "09-16": "16 de septiembre",
    "11-20": "20 de noviembre",
    "12-25": "25 de diciembre",
}

# Solo dominios de instituciones oficiales para las excepciones registradas.
DOMINIOS_OFICIALES = ("gob.mx", "diputados.gob.mx", "senado.gob.mx")
CAMPOS_CSV = (
    "fecha", "habil", "clasificacion", "motivo", "fundamento",
    "fuenteUrl", "esFinDeSemana", "fuenteBaseUrl",
)
ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fecha(fecha: str | date) -> date:
    if isinstance(fecha, date) and not hasattr(fecha, "hour"):
        return fecha
    if not isinstance(fecha, str) or not ISO_PATTERN.fullmatch(fecha):
        raise ValueError("La fecha debe usar YYYY-MM-DD, por ejemplo 2026-09-16")
    try:
        return date.fromisoformat(fecha)
    except ValueError as exc:
        raise ValueError(f"La fecha no existe: {fecha}") from exc


def _validar_url_oficial(url: object) -> str:
    if not isinstance(url, str):
        raise ValueError("Cada excepcion debe indicar fuenteUrl oficial")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or not any(
        host == sufijo or host.endswith("." + sufijo) for sufijo in DOMINIOS_OFICIALES
    ):
        raise ValueError(f"No parece ser un enlace HTTPS institucional oficial: {url}")
    return url


def _indexar_excepciones(registros: Iterable[Mapping[str, Any]] | None, tipo: str) -> dict[str, dict[str, str]]:
    resultado: dict[str, dict[str, str]] = {}
    if registros is None:
        return resultado
    if isinstance(registros, (str, bytes, Mapping)):
        raise TypeError(f"{tipo} debe ser una lista de objetos")
    for registro in registros:
        if not isinstance(registro, Mapping):
            raise TypeError(f"Registro invalido en {tipo}")
        fecha = _fecha(registro.get("fecha")).isoformat()
        motivo = registro.get("motivo")
        if not isinstance(motivo, str) or not motivo.strip():
            raise ValueError(f"La fecha {fecha} requiere un motivo")
        url = _validar_url_oficial(registro.get("fuenteUrl"))
        if fecha in resultado:
            raise ValueError(f"Fecha duplicada en {tipo}: {fecha}")
        resultado[fecha] = {"motivo": motivo.strip(), "fuenteUrl": url}
    return resultado


class CalendarioLFPA:
    """Consulta y exporta el calendario base de la LFPA; excepciones solo si hay fuente oficial.

    dias_adicionales: acuerdos de vacaciones generales/suspension de LABORES, confirmados.
    dias_habilitados: habilitaciones excepcionales de dias legalmente inhabiles, confirmadas.
    No use 'dias_adicionales' para suspensiones de plazos sin suspension de labores.
    """

    def __init__(
        self,
        dias_adicionales: Iterable[Mapping[str, Any]] | None = None,
        dias_habilitados: Iterable[Mapping[str, Any]] | None = None,
    ) -> None:
        self._adicionales = _indexar_excepciones(dias_adicionales, "dias_adicionales")
        self._habilitados = _indexar_excepciones(dias_habilitados, "dias_habilitados")
        simultaneos = set(self._adicionales) & set(self._habilitados)
        if simultaneos:
            raise ValueError(f"Fecha simultaneamente inhabil y habilitada: {sorted(simultaneos)[0]}")

    def consultar_fecha(self, fecha: str | date) -> dict[str, Any]:
        dia = _fecha(fecha)
        clave = dia.isoformat()
        fin_semana = dia.weekday() >= 5
        feriado = FERIADOS_FIJOS.get(dia.strftime("%m-%d"))
        if feriado:
            habil, clasificacion, motivo = False, "INHABIL_LFPA", feriado
        elif fin_semana:
            habil, clasificacion, motivo = False, "INHABIL_FIN_DE_SEMANA", "Sábado o domingo"
        else:
            habil, clasificacion, motivo = True, "HABIL_BASE_LFPA", "Día hábil en el calendario base LFPA"

        fundamento = "Artículo 28 de la LFPA"
        fuente_url = FUENTE_LFPA["url"]
        if clave in self._adicionales:
            x = self._adicionales[clave]
            habil, clasificacion, motivo = False, "INHABIL_ADICIONAL_VALIDADO", x["motivo"]
            fundamento, fuente_url = "Acuerdo oficial de suspensión de labores o vacaciones", x["fuenteUrl"]
        if clave in self._habilitados:
            x = self._habilitados[clave]
            habil, clasificacion, motivo = True, "HABILITADO_EXCEPCIONALMENTE", x["motivo"]
            fundamento, fuente_url = "Acuerdo oficial de habilitación", x["fuenteUrl"]

        return {
            "fecha": clave,
            "habil": habil,
            "clasificacion": clasificacion,
            "motivo": motivo,
            "fundamento": fundamento,
            "fuenteUrl": fuente_url,
            "esFinDeSemana": fin_semana,
            "fuenteBaseUrl": FUENTE_LFPA["url"],
        }

    def es_dia_habil(self, fecha: str | date) -> bool:
        return self.consultar_fecha(fecha)["habil"]

    def calendario_anual(self, anio: int) -> list[dict[str, Any]]:
        if type(anio) is not int or not 1900 <= anio <= 9999:
            raise ValueError("El anio debe ser un entero entre 1900 y 9999")
        actual = date(anio, 1, 1)
        ultimo = date(anio, 12, 31)
        resultado = []
        while True:
            resultado.append(self.consultar_fecha(actual))
            if actual == ultimo:
                break
            actual += timedelta(days=1)
        return resultado

    def dias_inhabiles(self, anio: int) -> list[dict[str, Any]]:
        return [x for x in self.calendario_anual(anio) if not x["habil"]]

    def siguiente_dia_habil(self, fecha: str | date) -> str:
        actual = _fecha(fecha)
        for _ in range(5000):
            actual += timedelta(days=1)
            if self.es_dia_habil(actual):
                return actual.isoformat()
        raise RuntimeError("No se encontro otro dia habil en los siguientes 5000 dias")

    def sumar_dias_habiles(self, fecha_inicio: str | date, dias: int) -> str:
        """Cuenta desde el dia SIGUIENTE, no incluye la fecha de inicio.

        La fecha legal exacta en que comienza un plazo depende del procedimiento.
        """
        actual = _fecha(fecha_inicio)
        if type(dias) is not int or not 1 <= dias <= 10000:
            raise ValueError("dias debe ser un entero de 1 a 10000")
        for _ in range(dias):
            actual = date.fromisoformat(self.siguiente_dia_habil(actual))
        return actual.isoformat()

    def exportar_csv(self, anio: int, archivo: str | Path) -> Path:
        destino = Path(archivo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, fieldnames=CAMPOS_CSV)
            escritor.writeheader()
            for fila in self.calendario_anual(anio):
                escritor.writerow(fila)
        return destino

    def exportar_json(self, anio: int, archivo: str | Path) -> Path:
        destino = Path(archivo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps({"fuente": FUENTE_LFPA, "anio": anio, "calendario": self.calendario_anual(anio)},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return destino


def desde_archivo_excepciones(archivo: str | Path | None = None) -> CalendarioLFPA:
    if archivo is None:
        return CalendarioLFPA()
    datos = json.loads(Path(archivo).read_text(encoding="utf-8-sig"))
    if not isinstance(datos, dict):
        raise ValueError("El archivo de excepciones debe contener un objeto JSON")
    return CalendarioLFPA(
        dias_adicionales=datos.get("diasAdicionales", []),
        dias_habilitados=datos.get("diasHabilitados", []),
    )


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Motor gratis de dias inhabiles LFPA con fuentes oficiales (sin dependencias).",
        epilog="Ejemplo: python lfpa.py consultar 2026-09-16",
    )
    parser.add_argument("--excepciones", metavar="EXCEPCIONES.JSON", help="Acuerdos adicionales verificados")
    comandos = parser.add_subparsers(dest="comando", required=True)
    sub_consulta = comandos.add_parser("consultar", help="Consultar una fecha")
    sub_consulta.add_argument("fecha", help="YYYY-MM-DD")
    sub_plazo = comandos.add_parser("calcular", help="Sumar dias habiles desde el dia posterior")
    sub_plazo.add_argument("fecha_inicio", help="YYYY-MM-DD")
    sub_plazo.add_argument("dias", type=int)
    sub_listar = comandos.add_parser("inhabiles", help="Listar dias inhabiles de un anio")
    sub_listar.add_argument("anio", type=int)
    sub_export = comandos.add_parser("exportar", help="Exportar los 365/366 dias del anio")
    sub_export.add_argument("anio", type=int)
    sub_export.add_argument("--formato", choices=("csv", "json"), default="csv")
    sub_export.add_argument("--salida", help="Archivo de salida")
    comandos.add_parser("fuente", help="Mostrar el fundamento oficial")
    args = parser.parse_args()
    try:
        motor = desde_archivo_excepciones(args.excepciones)
        if args.comando == "consultar":
            print(json.dumps(motor.consultar_fecha(args.fecha), ensure_ascii=False, indent=2))
        elif args.comando == "calcular":
            print(motor.sumar_dias_habiles(args.fecha_inicio, args.dias))
        elif args.comando == "inhabiles":
            print(json.dumps(motor.dias_inhabiles(args.anio), ensure_ascii=False, indent=2))
        elif args.comando == "exportar":
            ruta = args.salida or f"Calendario_LFPA_{args.anio}.{args.formato}"
            archivo = (motor.exportar_csv if args.formato == "csv" else motor.exportar_json)(args.anio, ruta)
            inhabiles = len(motor.dias_inhabiles(args.anio))
            print(f"Generado: {archivo} ({inhabiles} dias inhabiles base o validados)")
        elif args.comando == "fuente":
            print(json.dumps(FUENTE_LFPA, ensure_ascii=False, indent=2))
    except (ValueError, TypeError, OSError, OverflowError, json.JSONDecodeError) as exc:
        parser.exit(status=2, message=f"Error: {exc}\n")


if __name__ == "__main__":
    _cli()
