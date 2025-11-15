# Simulador de Sistemas Operativos – 2025-2

Este proyecto implementa un simulador básico de sistemas operativos en Python, incluyendo planificación de procesos, gestión de memoria con paginación y acceso concurrente a archivos mediante bloqueo.

## Ejecución

### 1. Requisitos
- Python 3.10 o superior
- No requiere librerías externas

### 2. Clonar el repositorio
```bash
git clone https://github.com/tuusuario/proyecto-operativos.git
cd proyecto-operativos
```

### 3. Ejecutar el simulador
```bash
python simulator_full.py
```

## Configuración del simulador

Puedes ajustar los algoritmos editando el archivo principal:

- Algoritmo de planificación: "RR", "SJF", "PRIORITY"
- Reemplazo de páginas: "FIFO" o "LRU"
- Número de frames de memoria
- Quantum del Round Robin

Ejemplo:

```python
sched = Scheduler(algorithm="RR", quantum=2)
mem = MemoryManager(num_frames=3, replacement="LRU")
```

## Ejemplo de salida

```
finished_count: 4
avg_waiting_time: 41.25
avg_turnaround_time: 48.25
cpu_utilization_percent: 44.06
page_faults: {1: 10, 2: 6, 3: 15, 4: 2}
file_conflicts: 0
time_elapsed: 61
```

## Estructura del proyecto

```
simulator_full.py   # Código principal del simulador
README.md           # Documentación del repositorio
```

## Documentación

El informe técnico detallado se encuentra fuera de este repositorio según las entregas del curso.

## Autor

Proyecto académico – Sistemas Operativos 2025-2.
