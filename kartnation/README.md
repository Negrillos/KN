# 🏁 KartPro — Plataforma de Reservas de Karting

Aplicación web de reservas de karting inspirada en Playtomic, construida con Flask y SQLite.

## 🚀 Instalación y Arranque

### 1. Instalar dependencias
```bash
pip install flask
```

### 2. Arrancar la aplicación
```bash
cd kartodromo
python app.py
```

### 3. Abrir en el navegador
```
http://localhost:5000
```

---

## 📋 Funcionalidades

### 🏎️ Circuitos disponibles
- **6 circuitos** distintos repartidos por España
- Detalles de cada circuito: longitud, velocidad máxima, dificultad, tipo (indoor/outdoor)
- Precios por tanda, número máximo de pilotos

### 👤 Sistema de usuarios
- Registro de cuenta con datos del piloto (nombre, edad, experiencia)
- Inicio y cierre de sesión
- Perfil de piloto con estadísticas
- **Niveles de karting**: Novato → Amateur → Intermedio → Avanzado → Profesional → Experto
  *(Los niveles se asignan por lógica interna — pendiente de implementar parámetros)*

### 📅 Sistema de reservas
- Tandas disponibles de **08:00 a 18:00**, cada **15 minutos**
- Selector de fecha (no permite fechas pasadas)
- Visualización de ocupación en tiempo real (libre / casi llena / completa)
- Al hacer clic en una tanda → modal con los pilotos apuntados y sus niveles
- Cancelación de reservas desde el perfil

### 📊 Visibilidad social
- Cada tanda muestra los pilotos inscritos con:
  - Nombre completo y username
  - Nivel de karting (con color e icono)
  - Número de carreras completadas

---

## 🗂️ Estructura del proyecto

```
kartodromo/
├── app.py                  # Aplicación Flask principal
├── requirements.txt        # Dependencias
├── kartodromo.db           # Base de datos SQLite (se crea automáticamente)
└── templates/
    ├── base.html           # Layout base con nav y estilos globales
    ├── index.html          # Página principal con grid de circuitos
    ├── register.html       # Registro de usuarios
    ├── login.html          # Inicio de sesión
    ├── circuit.html        # Detalle de circuito con slots de reserva
    └── profile.html        # Perfil del piloto con sus reservas
```

---

## 🔧 Próximos pasos (backend de niveles)

El sistema de niveles está preparado para recibir parámetros. En `app.py` existe la función
`get_karting_level_info()` y el campo `karting_level` en la tabla `users`.

Parámetros sugeridos para calcular el nivel automáticamente:
- Mejor tiempo de vuelta por circuito
- Tiempo medio de vuelta
- Número de carreras completadas
- Consistencia (desviación estándar de tiempos)
- Comparativa con otros pilotos del mismo circuito

---

## 🎨 Tecnologías

- **Backend**: Python 3 + Flask + SQLite
- **Frontend**: HTML5 + CSS3 (vanilla, sin frameworks)
- **Tipografías**: Bebas Neue + Barlow (Google Fonts)
- **Diseño**: Racing/industrial, tema oscuro, acentos en naranja/dorado/cyan
