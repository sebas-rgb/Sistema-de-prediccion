# Sistema de Gestión de Tickets - Austral Lens

Backend desarrollado con Spring Boot 4.0.2, Spring Security 7.0.2 y MySQL.
Sistema de soporte técnico integral para la gestión de tickets de incidencias.

## Descripción del Proyecto

Sistema web de gestión de tickets que permite a los usuarios registrar solicitudes de soporte técnico, adjuntar evidencias multimedia y dar seguimiento a sus casos. Incluye panel administrativo con estadísticas en tiempo real y generación de reportes en Excel.

## Configuración de Roles y Seguridad

### Roles del Sistema

- **ADMIN**: Acceso completo al panel administrativo y gestión de tickets
- **EDITOR**: Gestión de tickets asignados
- **USER**: Creación y seguimiento de propios tickets

### Rutas Protegidas

```
/admin/**              → Solo ADMIN
/menu                  → USER, EDITOR, ADMIN
/perfil                → USER, EDITOR, ADMIN
/tickets/**            → USER, EDITOR, ADMIN
/recuperar             → Público (sin autenticación)
```

Todos los roles se normalizan a ROLE_[NOMBRE] en Spring Security.

## Funcionalidades Principales

### Módulo de Tickets

- Creación de tickets con categorización
- Adjuntar múltiples archivos (máximo 10MB por archivo, 50MB total)
- Historial de solicitudes del usuario
- Estados: Abierto, En progreso, Cerrado
- Niveles de prioridad: Baja, Media, Alta

### Panel Administrativo

**Ruta**: `GET /admin/dashboard`

Métricas disponibles:
- Total de usuarios registrados
- Total de tickets creados
- Tickets cerrados vs abiertos
- Distribución por sede
- Estadísticas por período

Visualizaciones:
- Gráficos de línea para tickets creados por período
- Gráficos de línea para tickets cerrados por período
- Gráfico de pastel para distribución por sede

### Reportes en Excel

**Ruta**: `GET /admin/dashboard/reporte?year=YYYY&month=MM`

Genera archivo Excel con tres hojas:

1. **Resumen Mensual**: Indicadores clave del período
2. **Detalle de Tickets**: Listado completo con columnas (ID, Fecha, Usuario, Correo, Teléfono, Tema, Descripción, Sede, Estado, Prioridad)
3. **Tickets por Sede**: Consolidado de volumen por ubicación

Características:
- Formato profesional con encabezados congelados
- Filtros automáticos habilitados
- Fechas formateadas (dd/MM/yyyy HH:mm)
- Colores de estado para mejor visualización

## Stack Tecnológico

### Backend

- **Java 21**
- **Spring Boot 4.0.2**
- **Spring Security 7.0.2**
- **Spring Data JPA**
- **Hibernate 6.4.0**
- **MySQL 8.0**
- **Apache POI 5.4.0** (Generación de Excel)

### Frontend

- **Thymeleaf 3.1.2**
- **TailwindCSS 3.3.0**
- **Font Awesome 6.4.0**
- **Chart.js 4.4.1**
- **Vanilla JavaScript**

### Herramientas

- **Maven 3.9.2**
- **Spring DevTools**
- **Spring Session JDBC**

## Instalación y Configuración

### Requisitos Previos

- Java 21 JDK
- MySQL 8.0 o superior
- Maven 3.9+

### Pasos de Instalación

1. **Clonar el repositorio**
```bash
git clone <url-repositorio>
cd austral-springboot
```

2. **Crear base de datos**
```sql
CREATE DATABASE austral_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

3. **Configurar conexión** (application.properties)
```properties
spring.datasource.url=jdbc:mysql://localhost:3306/austral_db
spring.datasource.username=usuario
spring.datasource.password=contraseña
spring.datasource.driverClassName=com.mysql.cj.jdbc.Driver

spring.jpa.hibernate.ddl-auto=update
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.MySQLDialect
```

4. **Compilar y ejecutar**
```bash
./mvnw clean install
./mvnw spring-boot:run
```

La aplicación estará disponible en `http://localhost:80`

## Configuración de Multipart

Límites configurados para carga de archivos:
- Máximo por archivo: 10 MB
- Máximo por solicitud: 50 MB
- Máximo de archivos: 10

Configuración en `application.properties`:
```properties
spring.servlet.multipart.max-file-size=10MB
spring.servlet.multipart.max-request-size=50MB
```

## Configuración para Producción

Para ambientes de producción:

1. **Desactivar DDL automático**
```properties
spring.jpa.hibernate.ddl-auto=validate
```

2. **Mantener CSRF habilitado** (ya está por defecto)

3. **Usar variables de entorno** para credenciales
```bash
export DB_USERNAME=usuario
export DB_PASSWORD=contraseña
```

4. **Compilar WAR**
```bash
./mvnw clean package -DskipTests
```

El archivo `back-0.0.1-SNAPSHOT.war` estará disponible en `target/`

## Estructura del Proyecto

```
src/main/
├── java/com/maple/back/
│   ├── controller/          # Controladores REST
│   ├── service/             # Lógica de negocio
│   ├── repository/          # Acceso a datos
│   ├── model/               # Entidades JPA
│   ├── configuration/       # Configuración Spring
│   └── BackApplication.java # Punto de entrada
└── resources/
    ├── templates/           # Vistas Thymeleaf
    ├── static/              # Archivos CSS, JS, imágenes
    └── application.properties
```

## Estado del Sistema

- Seguridad: Configurada y validada
- Base de datos: Normalizada y consistente
- Validación: Roles alineados con Spring Security
- Dashboard: Operativo con estadísticas en tiempo real
- Reportes: Generación exitosa de archivos Excel
- Sistema: Estable y funcional

## Licencia

Desarrollado para Austral Lens Colombia. Todos los derechos reservados © 2026
