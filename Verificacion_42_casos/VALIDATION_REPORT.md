# Reporte de validación SIGTB (piloto TFM)

Generado: `2026-09-14T00:24:06Z`

- Casos: **42**
- Aprobados: **42**
- Fallidos: **0**
- Críticos fallidos: ninguno
- Frontera fallidos: ninguno

| ID | Requisito | Tipo | Crítico | Conformidad | Detalle |
|----|-----------|------|---------|-------------|---------|
| `SUF-01` | Suficiencia mixto: D, Ceq, Rd, Rc, Rm, Rb, Rfinal, S, Alerta | nominal | sí | SÍ | — |
| `SUF-02` | Suficiencia frontera S=1 -> Suficiente | frontera | sí | SÍ | — |
| `SUF-03` | Suficiencia S<0.80 -> Insuficiente | nominal | sí | SÍ | — |
| `SUF-04` | Suficiencia Rfinal=0 -> Revisar (sin división por cero) | error | sí | SÍ | — |
| `SUF-05` | Suficiencia demanda sin H,u,t -> Revisar | error | sí | SÍ | — |
| `SUF-06` | Suficiencia t>H -> Revisar | error | sí | SÍ | — |
| `SUF-07` | Suficiencia modo demanda: Rb=Rd | nominal | no | SÍ | — |
| `SUF-08` | Suficiencia modo concurrencia: Rc=ceil(Q), Rb=Rc | nominal | no | SÍ | — |
| `SUF-09` | Suficiencia alias legado -> 4 modos TFM | nominal | no | SÍ | — |
| `DIM-01` | Dimensionamiento excluye comodato/leasing/baja de Hparque y Nc | nominal | sí | SÍ | — |
| `DIM-02` | Leasing fuera de plantilla y Hparque=0 | nominal | sí | SÍ | — |
| `DIM-03` | Nh (carga) y Nc (criticidad) se calculan por funciones distintas | nominal | sí | SÍ | — |
| `DIM-04` | Nc=ceil(Σ Ek/rk) no suma de techos | frontera | sí | SÍ | — |
| `DIM-05` | Hnom=42·52 y Hdisp=(Hnom)·p | nominal | no | SÍ | — |
| `GE-01` | GE=F+A+M+Hf | nominal | sí | SÍ | — |
| `GE-02` | GE con componente faltante -> Revisar | error | sí | SÍ | — |
| `GE-03` | Frontera GE 11 vs 12 | frontera | sí | SÍ | — |
| `GE-04` | Frontera GE 14 vs 15 | frontera | sí | SÍ | — |
| `GE-05` | Frontera GE 18 vs 19 | frontera | sí | SÍ | — |
| `GE-06` | GE≥12: TPM=min(TGE,Tfab) | nominal | sí | SÍ | — |
| `GE-07` | GE<12: prevalece fabricante si hay Tfab | nominal | sí | SÍ | — |
| `PRE-01` | Csitio 89% -> No aprobado | frontera | sí | SÍ | — |
| `PRE-02` | Csitio 90% sin críticos incumplidos ni pendientes -> Aprobado | frontera | sí | SÍ | — |
| `PRE-03` | Csitio 100% -> Aprobado | nominal | no | SÍ | — |
| `PRE-04` | 90% con pendientes (no crítico incumplido) -> Aprobado con condiciones | frontera | sí | SÍ | — |
| `PRE-05` | Crítico No cumple -> No aprobado aunque Csitio≥90 | nominal | sí | SÍ | — |
| `PRE-06` | Σ ai=0 -> Revisar | error | sí | SÍ | — |
| `RBAC-01` | Técnico no abre instrumentos de ingeniería | nominal | sí | SÍ | — |
| `RBAC-02` | Ingeniero ve instrumentos y no edita sedes sin overlay | nominal | sí | SÍ | — |
| `RBAC-03` | JOB pendiente -> sin permisos | error | sí | SÍ | — |
| `RBAC-04` | ADMIN alcanza cualquier empresa | nominal | sí | SÍ | — |
| `RBAC-05` | Operativo no cruza de empresa | nominal | sí | SÍ | — |
| `RBAC-06` | Matriz RBAC mapea jobs de instrumentos a permisos atómicos | nominal | no | SÍ | — |
| `IMP-01` | Importación CSV con encabezados requeridos | nominal | sí | SÍ | — |
| `IMP-02` | Importación XLSX rechazada (error controlado) | error | no | SÍ | — |
| `IMP-03` | CSV vacío -> error controlado | error | no | SÍ | — |
| `EXP-01` | Exportación CSV incluye EQUIPO y mapea fila | nominal | sí | SÍ | — |
| `FLW-01` | Flujo principal: rutas del piloto registradas | nominal | sí | SÍ | — |
| `FLW-02` | Catálogo de fórmulas TFM-1.0 persistible | nominal | sí | SÍ | — |
| `FLW-03` | UI piloto expone paneles del flujo principal | nominal | no | SÍ | — |
| `BKP-01` | Respaldo SQLite y restauracion tras corrupcion | nominal | sí | SÍ | — |
| `BKP-02` | Restauracion rechaza path escape | error | sí | SÍ | — |

## Registro por caso

### `SUF-01` — Suficiencia mixto: D, Ceq, Rd, Rc, Rm, Rb, Rfinal, S, Alerta

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "modo": "mixto",
  "H": 12,
  "u": 0.75,
  "t_h": 0.5,
  "P": 40,
  "Q": 4,
  "Rm": 2,
  "b": 0.2,
  "D": 4
}
```

- Esperado:

```json
{
  "D": 4,
  "Ceq": 18,
  "Rd": 3,
  "Rc": 4,
  "Rm": 2,
  "Rb": 4,
  "Rfinal": 5,
  "S": 0.8,
  "resultado": "Alerta"
}
```

- Obtenido:

```json
{
  "D": 4,
  "Ceq": 18.0,
  "Rd": 3.0,
  "Rc": 4.0,
  "Rm": 2.0,
  "Rb": 4.0,
  "Rfinal": 5.0,
  "S": 0.8,
  "resultado": "Alerta"
}
```

### `SUF-02` — Suficiencia frontera S=1 -> Suficiente

- Tipo: frontera · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "modo": "minimo",
  "Rm": 4,
  "D": 4,
  "b": 0
}
```

- Esperado:

```json
{
  "S": 1.0,
  "resultado": "Suficiente"
}
```

- Obtenido:

```json
{
  "S": 1.0,
  "resultado": "Suficiente"
}
```

### `SUF-03` — Suficiencia S<0.80 -> Insuficiente

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "modo": "minimo",
  "Rm": 10,
  "D": 7,
  "b": 0
}
```

- Esperado:

```json
{
  "S": 0.7,
  "resultado": "Insuficiente"
}
```

- Obtenido:

```json
{
  "S": 0.7,
  "resultado": "Insuficiente"
}
```

### `SUF-04` — Suficiencia Rfinal=0 -> Revisar (sin división por cero)

- Tipo: error · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "modo": "minimo",
  "Rm": 0,
  "D": 4
}
```

- Esperado:

```json
{
  "resultado": "Revisar",
  "S": null
}
```

- Obtenido:

```json
{
  "resultado": "Revisar",
  "S": null
}
```

### `SUF-05` — Suficiencia demanda sin H,u,t -> Revisar

- Tipo: error · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "modo": "demanda",
  "P": 40,
  "H": null,
  "t": null
}
```

- Esperado:

```json
"Revisar"
```

- Obtenido:

```json
"Revisar"
```

### `SUF-06` — Suficiencia t>H -> Revisar

- Tipo: error · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "t": 20,
  "H": 8,
  "P": 10
}
```

- Esperado:

```json
"Revisar"
```

- Obtenido:

```json
"Revisar"
```

### `SUF-07` — Suficiencia modo demanda: Rb=Rd

- Tipo: nominal
- Conformidad: **SÍ**
- Entradas:

```json
{
  "modo": "demanda",
  "P": 40,
  "H": 12,
  "u": 0.75,
  "t": 0.5,
  "b": 0
}
```

- Esperado:

```json
{
  "Ceq": 18,
  "Rd": 3,
  "Rb": 3,
  "Rfinal": 3,
  "modo": "demanda"
}
```

- Obtenido:

```json
{
  "Ceq": 18.0,
  "Rd": 3.0,
  "Rb": 3.0,
  "Rfinal": 3.0,
  "modo": "demanda"
}
```

### `SUF-08` — Suficiencia modo concurrencia: Rc=ceil(Q), Rb=Rc

- Tipo: nominal
- Conformidad: **SÍ**
- Entradas:

```json
{
  "modo": "concurrencia",
  "Q": 4,
  "b": 0
}
```

- Esperado:

```json
{
  "Rc": 4,
  "Rb": 4,
  "Rfinal": 4,
  "modo": "concurrencia"
}
```

- Obtenido:

```json
{
  "Rc": 4.0,
  "Rb": 4.0,
  "Rfinal": 4.0,
  "modo": "concurrencia"
}
```

### `SUF-09` — Suficiencia alias legado -> 4 modos TFM

- Tipo: nominal
- Conformidad: **SÍ**
- Entradas:

```json
{
  "aliases": [
    "por_demanda",
    "por_capacidad",
    "principal",
    "minimo_tecnico",
    "esterilizacion_rotacion"
  ]
}
```

- Esperado:

```json
{
  "por_demanda": "demanda",
  "por_capacidad": "concurrencia",
  "principal": "concurrencia",
  "minimo_tecnico": "minimo",
  "esterilizacion_rotacion": "demanda"
}
```

- Obtenido:

```json
{
  "por_demanda": "demanda",
  "por_capacidad": "concurrencia",
  "principal": "concurrencia",
  "minimo_tecnico": "minimo",
  "esterilizacion_rotacion": "demanda"
}
```

### `DIM-01` — Dimensionamiento excluye comodato/leasing/baja de Hparque y Nc

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "formas": [
    "Compra directa",
    "Comodato",
    "BAJA"
  ]
}
```

- Esperado:

```json
{
  "Hnom": 2184,
  "internos": 1,
  "tercerizados": 1,
  "Hparque": 6.9,
  "comodato_horas": 0.0,
  "baja_dotacion": false,
  "Nc_equipos": 1,
  "fuera_plantilla": 1
}
```

- Obtenido:

```json
{
  "Hnom": 2184.0,
  "internos": 1,
  "tercerizados": 1,
  "Hparque": 6.9,
  "comodato_horas": 0.0,
  "baja_dotacion": false,
  "Nc_equipos": 1,
  "fuera_plantilla": 1
}
```

### `DIM-02` — Leasing fuera de plantilla y Hparque=0

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "forma": "Leasing",
  "cal_h": 3,
  "mp_h": 8
}
```

- Esperado:

```json
{
  "en_plantilla": false,
  "total_horas": 0.0
}
```

- Obtenido:

```json
{
  "en_plantilla": false,
  "total_horas": 0.0
}
```

### `DIM-03` — Nh (carga) y Nc (criticidad) se calculan por funciones distintas

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "Hparque": 100,
  "Hdisp": 2184,
  "Ek_medio": 1,
  "rk": 50
}
```

- Esperado:

```json
{
  "Nh": 1.0,
  "Nc": 1.0,
  "resumen_tiene_nc": false,
  "ic_tiene_hdisp": false
}
```

- Obtenido:

```json
{
  "Nh": 1.0,
  "Nc": 1.0,
  "resumen_tiene_nc": false,
  "ic_tiene_hdisp": false
}
```

### `DIM-04` — Nc=ceil(Σ Ek/rk) no suma de techos

- Tipo: frontera · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "Bajo": 40,
  "Medio": 30,
  "Alto": 5,
  "rk": [
    70,
    50,
    20
  ]
}
```

- Esperado:

```json
{
  "Nc": 2.0,
  "suma_techos": 3.0
}
```

- Obtenido:

```json
{
  "Nc": 2.0,
  "suma_techos": 3.0
}
```

### `DIM-05` — Hnom=42·52 y Hdisp=(Hnom)·p

- Tipo: nominal
- Conformidad: **SÍ**
- Entradas:

```json
{
  "Hs": 42,
  "semanas": 52,
  "p": 0.8
}
```

- Esperado:

```json
{
  "Hnom": 2184.0,
  "Hdisp": 1747.2
}
```

- Obtenido:

```json
{
  "Hnom": 2184.0,
  "Hdisp": 1747.2
}
```

### `GE-01` — GE=F+A+M+Hf

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "F": 10,
  "A": 5,
  "M": 3,
  "Hf": 2
}
```

- Esperado:

```json
20.0
```

- Obtenido:

```json
20.0
```

### `GE-02` — GE con componente faltante -> Revisar

- Tipo: error · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "F": 10,
  "A": 5,
  "M": 3,
  "Hf": null,
  "Tfab": 6
}
```

- Esperado:

```json
{
  "GE": null,
  "frecuencia": "Revisar"
}
```

- Obtenido:

```json
{
  "GE": null,
  "frecuencia": "Revisar"
}
```

### `GE-03` — Frontera GE 11 vs 12

- Tipo: frontera · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "GE": [
    11,
    12
  ]
}
```

- Esperado:

```json
{
  "tge_11": null,
  "tge_12": 12,
  "lab_11": "Correctivo bajo demanda",
  "lab_12": "Anual"
}
```

- Obtenido:

```json
{
  "tge_11": null,
  "tge_12": 12,
  "lab_11": "Correctivo bajo demanda",
  "lab_12": "Anual"
}
```

### `GE-04` — Frontera GE 14 vs 15

- Tipo: frontera · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "GE": [
    14,
    15
  ]
}
```

- Esperado:

```json
{
  "tge_14": 12,
  "tge_15": 6,
  "lab_15": "Cada 6 meses"
}
```

- Obtenido:

```json
{
  "tge_14": 12,
  "tge_15": 6,
  "lab_15": "Cada 6 meses"
}
```

### `GE-05` — Frontera GE 18 vs 19

- Tipo: frontera · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "GE": [
    18,
    19
  ]
}
```

- Esperado:

```json
{
  "tge_18": 6,
  "tge_19": 4,
  "lab_19": "Cada 4 meses"
}
```

- Obtenido:

```json
{
  "tge_18": 6,
  "tge_19": 4,
  "lab_19": "Cada 4 meses"
}
```

### `GE-06` — GE≥12: TPM=min(TGE,Tfab)

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "GE": 20,
  "TGE": 4,
  "Tfab": [
    6,
    3
  ]
}
```

- Esperado:

```json
{
  "vs6": "Cada 4 meses",
  "vs3": "PM fabricante cada 3 meses"
}
```

- Obtenido:

```json
{
  "vs6": "Cada 4 meses",
  "vs3": "PM fabricante cada 3 meses"
}
```

### `GE-07` — GE<12: prevalece fabricante si hay Tfab

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "GE": 11,
  "Tfab": 6
}
```

- Esperado:

```json
"PM fabricante cada 6 meses"
```

- Obtenido:

```json
"PM fabricante cada 6 meses"
```

### `PRE-01` — Csitio 89% -> No aprobado

- Tipo: frontera · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "cumple": 89,
  "no_cumple": 11
}
```

- Esperado:

```json
{
  "pct": 0.89,
  "decision": "No aprobado para instalación"
}
```

- Obtenido:

```json
{
  "pct": 0.89,
  "decision": "No aprobado para instalación"
}
```

### `PRE-02` — Csitio 90% sin críticos incumplidos ni pendientes -> Aprobado

- Tipo: frontera · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "cumple": 90,
  "no_cumple_mayor": 10
}
```

- Esperado:

```json
{
  "pct": 0.9,
  "criticos_incumplidos": 0,
  "decision": "Aprobado para instalación"
}
```

- Obtenido:

```json
{
  "pct": 0.9,
  "criticos_incumplidos": 0,
  "decision": "Aprobado para instalación"
}
```

### `PRE-03` — Csitio 100% -> Aprobado

- Tipo: nominal
- Conformidad: **SÍ**
- Entradas:

```json
{
  "cumple": 100
}
```

- Esperado:

```json
{
  "pct": 1,
  "decision": "Aprobado para instalación"
}
```

- Obtenido:

```json
{
  "pct": 1.0,
  "decision": "Aprobado para instalación"
}
```

### `PRE-04` — 90% con pendientes (no crítico incumplido) -> Aprobado con condiciones

- Tipo: frontera · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "cumple": 90,
  "pendiente": 10
}
```

- Esperado:

```json
"Aprobado con condiciones"
```

- Obtenido:

```json
"Aprobado con condiciones"
```

### `PRE-05` — Crítico No cumple -> No aprobado aunque Csitio≥90

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "cumple": 90,
  "critico_no_cumple": 1
}
```

- Esperado:

```json
{
  "criticos_incumplidos": 1,
  "decision": "No aprobado para instalación"
}
```

- Obtenido:

```json
{
  "criticos_incumplidos": 1,
  "decision": "No aprobado para instalación"
}
```

### `PRE-06` — Σ ai=0 -> Revisar

- Tipo: error · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "estado": "No aplica"
}
```

- Esperado:

```json
{
  "evaluables": 0,
  "pct": null,
  "decision": "Revisar"
}
```

- Obtenido:

```json
{
  "evaluables": 0,
  "pct": null,
  "decision": "Revisar"
}
```

### `RBAC-01` — Técnico no abre instrumentos de ingeniería

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "ROLL": "OPERATIVO",
  "JOB": "Técnico"
}
```

- Esperado:

```json
{
  "view_suficiencia": false,
  "view_dimensionamiento": false,
  "view_frecuencia_pm": false,
  "view_preinstalacion": false
}
```

- Obtenido:

```json
{
  "view_suficiencia": false,
  "view_dimensionamiento": false,
  "view_frecuencia_pm": false,
  "view_preinstalacion": false
}
```

### `RBAC-02` — Ingeniero ve instrumentos y no edita sedes sin overlay

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "ROLL": "OPERATIVO",
  "JOB": "Ingeniero"
}
```

- Esperado:

```json
{
  "view_suficiencia": true,
  "modify_sede": false,
  "request_expanded_permissions": true
}
```

- Obtenido:

```json
{
  "view_suficiencia": true,
  "modify_sede": false,
  "request_expanded_permissions": true
}
```

### `RBAC-03` — JOB pendiente -> sin permisos

- Tipo: error · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "ROLL": "OPERATIVO",
  "JOB": ""
}
```

- Esperado:

```json
0
```

- Obtenido:

```json
0
```

### `RBAC-04` — ADMIN alcanza cualquier empresa

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "ROLL": "ADMIN",
  "empresa_id": null,
  "target": 99
}
```

- Esperado:

```json
true
```

- Obtenido:

```json
true
```

### `RBAC-05` — Operativo no cruza de empresa

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "empresa_id": 7,
  "target_ok": 7,
  "target_no": 8
}
```

- Esperado:

```json
{
  "misma": true,
  "otra": false
}
```

- Obtenido:

```json
{
  "misma": true,
  "otra": false
}
```

### `RBAC-06` — Matriz RBAC mapea jobs de instrumentos a permisos atómicos

- Tipo: nominal
- Conformidad: **SÍ**
- Entradas:

```json
{
  "jobs": [
    "Suficiencia de equipos",
    "Dimensionamiento de personal",
    "Frecuencia de mantenimiento preventivo",
    "Preinstalación de la tecnología biomédica"
  ]
}
```

- Esperado:

```json
{
  "Suficiencia de equipos": [
    "view_suficiencia"
  ],
  "Dimensionamiento de personal": [
    "view_dimensionamiento"
  ],
  "Frecuencia de mantenimiento preventivo": [
    "view_frecuencia_pm"
  ],
  "Preinstalación de la tecnología biomédica": [
    "view_preinstalacion"
  ]
}
```

- Obtenido:

```json
{
  "Suficiencia de equipos": [
    "view_suficiencia"
  ],
  "Dimensionamiento de personal": [
    "view_dimensionamiento"
  ],
  "Frecuencia de mantenimiento preventivo": [
    "view_frecuencia_pm"
  ],
  "Preinstalación de la tecnología biomédica": [
    "view_preinstalacion"
  ]
}
```

### `IMP-01` — Importación CSV con encabezados requeridos

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "archivo": "inventario.csv",
  "filas": 1
}
```

- Esperado:

```json
{
  "error": null,
  "n": 1,
  "equipo": "Monitor"
}
```

- Obtenido:

```json
{
  "error": null,
  "n": 1,
  "equipo": "Monitor"
}
```

### `IMP-02` — Importación XLSX rechazada (error controlado)

- Tipo: error
- Conformidad: **SÍ**
- Entradas:

```json
{
  "archivo": "datos.xlsx"
}
```

- Esperado:

```json
{
  "rows": null,
  "csv_en_error": true
}
```

- Obtenido:

```json
{
  "rows": null,
  "csv_en_error": true
}
```

### `IMP-03` — CSV vacío -> error controlado

- Tipo: error
- Conformidad: **SÍ**
- Entradas:

```json
{
  "archivo": "vacio.csv",
  "bytes": 3
}
```

- Esperado:

```json
{
  "rows": null,
  "vacio": true
}
```

- Obtenido:

```json
{
  "rows": null,
  "vacio": true
}
```

### `EXP-01` — Exportación CSV incluye EQUIPO y mapea fila

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "equipo": "Bomba",
  "aplica_mp": 1
}
```

- Esperado:

```json
{
  "tiene_equipo": true,
  "valor": "Bomba"
}
```

- Obtenido:

```json
{
  "tiene_equipo": true,
  "valor": "Bomba"
}
```

### `FLW-01` — Flujo principal: rutas del piloto registradas

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "rutas_exigidas": [
    "/",
    "/api/dimensionamiento/meta",
    "/api/frecuencia-pm/meta",
    "/api/preinstalacion/meta",
    "/api/servicios/<int:servicio_id>/inventario/export.csv",
    "/api/servicios/<int:servicio_id>/inventario/import",
    "/api/suficiencia/meta"
  ]
}
```

- Esperado:

```json
[]
```

- Obtenido:

```json
[]
```

### `FLW-02` — Catálogo de fórmulas TFM-1.0 persistible

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "modulos": [
    "dimensionamiento",
    "ge",
    "preinstalacion",
    "suficiencia"
  ]
}
```

- Esperado:

```json
{
  "mods": [
    "dimensionamiento",
    "ge",
    "preinstalacion",
    "suficiencia"
  ],
  "versions": {
    "dimensionamiento": "TFM-1.0",
    "ge": "TFM-1.0",
    "preinstalacion": "TFM-1.0",
    "suficiencia": "TFM-1.0"
  }
}
```

- Obtenido:

```json
{
  "mods": [
    "dimensionamiento",
    "ge",
    "preinstalacion",
    "suficiencia"
  ],
  "versions": {
    "dimensionamiento": "TFM-1.0",
    "ge": "TFM-1.0",
    "preinstalacion": "TFM-1.0",
    "suficiencia": "TFM-1.0"
  }
}
```

### `FLW-03` — UI piloto expone paneles del flujo principal

- Tipo: nominal
- Conformidad: **SÍ**
- Entradas:

```json
{
  "archivo": "public/index.html"
}
```

- Esperado:

```json
{
  "suficiencia": true,
  "dimensionamiento": true,
  "ge": true,
  "preinstalacion": true,
  "bandeja": true
}
```

- Obtenido:

```json
{
  "suficiencia": true,
  "dimensionamiento": true,
  "ge": true,
  "preinstalacion": true,
  "bandeja": true
}
```

### `BKP-01` — Respaldo SQLite y restauracion tras corrupcion

- Tipo: nominal · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "copied": 4,
  "corrupcion": "empresas.db"
}
```

- Esperado:

```json
{
  "ok": true,
  "copied": 4,
  "restored": true,
  "valor": 5
}
```

- Obtenido:

```json
{
  "ok": true,
  "copied": 4,
  "restored": true,
  "valor": 5
}
```

### `BKP-02` — Restauracion rechaza path escape

- Tipo: error · crítico
- Conformidad: **SÍ**
- Entradas:

```json
{
  "snapshot_id": "../secret"
}
```

- Esperado:

```json
false
```

- Obtenido:

```json
false
```

