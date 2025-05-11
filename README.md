# Sistema de Gestión de Logs de Estaciones Meteorológicas

Este proyecto implementa un sistema para recolectar, procesar y almacenar logs de datos de estaciones meteorológicas utilizando Python, RabbitMQ, PostgreSQL y Docker.

## Arquitectura del Sistema

1.  **Productores de Datos (`producer`):** Un servicio en Python que simula la generación de datos de estaciones meteorológicas en formato JSON. Publica estos mensajes en un exchange de RabbitMQ. Los mensajes son marcados como persistentes.
2.  **Broker de Mensajería (RabbitMQ):** RabbitMQ actúa como el intermediario de mensajes. Se configura un exchange (`weather_exchange`) y una cola durable (`weather_log_queue`). Los mensajes son persistentes para evitar pérdidas. El dashboard de administración de RabbitMQ está disponible en `http://localhost:15672`.
3.  **Consumidores (`consumer`):** Un microservicio en Python que consume mensajes de la cola de RabbitMQ.
    * Procesa mensajes con acknowledgement manual (`ack`).
    * Utiliza `prefetch_count=1` para un procesamiento ordenado.
    * Valida los datos recibidos contra rangos predefinidos.
    * Persiste los datos (válidos e inválidos con sus errores) en una base de datos PostgreSQL.
    * Maneja errores de conexión y procesamiento.
4.  **Base de Datos (PostgreSQL):** Una base de datos PostgreSQL para almacenar los logs meteorológicos en la tabla `weather_logs`. Los datos de la base de datos son persistentes utilizando volúmenes Docker.
5.  **Orquestación (Docker Compose):** Todos los componentes (productor, consumidor, RabbitMQ, PostgreSQL) están contenerizados y orquestados mediante `docker-compose.yml`. Se asegura un arranque ordenado (usando `depends_on` y `healthcheck`) y reinicios automáticos en caso de fallo.

## Requisitos Previos

* Docker Compose

## Configuración

Las configuraciones principales se encuentran en:
* `docker-compose.yml`: Define los servicios, redes, volúmenes y variables de entorno.
* Variables de entorno en `docker-compose.yml` para usuarios/contraseñas de RabbitMQ y PostgreSQL.

### Variables de Entorno Clave

* **RabbitMQ:** `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`
* **PostgreSQL:** `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
* **Productor/Consumidor:** Referencian los servicios por sus nombres en `docker-compose.yml` (ej. `rabbitmq`, `postgres`).

## Cómo Ejecutar el Sistema

1.  Clona este repositorio.
2.  Navega al directorio raíz del proyecto.
3.  Ejecuta el siguiente comando para construir y levantar los contenedores:
    ```bash
    docker-compose up --build -d
    ```
    El `-d` ejecuta los contenedores en segundo plano.

4.  Para ver los logs de los servicios:
    ```bash
    docker-compose logs -f producer
    docker-compose logs -f consumer
    docker-compose logs -f rabbitmq
    docker-compose logs -f postgres
    ```
    (Usa `-f` para seguir los logs en tiempo real).

5.  Para detener el sistema:
    ```bash
    docker-compose down
    ```

6.  Para detener y eliminar los volúmenes (¡cuidado, esto borrará los datos persistidos!):
    ```bash
    docker-compose down -v
    ```

## Acceso a Servicios

* **RabbitMQ Management Dashboard:** `http://localhost:15672` 
Usuario: userRpx
Contraseña: pd3edeW246

* **PostgreSQL:** Puede ser accedido en `localhost:5432` con un cliente de base de datos (ej. pgAdmin, DBeaver) usando las credenciales:
    * Host: `localhost`
    * Puerto: `5432`
    * Usuario: `weatheruser`
    * Contraseña: `weatherpass`
    * Base de datos: `weatherdb`

## Esquema de la Base de Datos

La base de datos `weatherdb` contiene la tabla `weather_logs`:

```sql
CREATE TABLE IF NOT EXISTS weather_logs (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    temperature_celsius REAL,
    humidity_percent REAL,
    pressure_hpa REAL,
    wind_speed_kmh REAL,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_valid BOOLEAN DEFAULT TRUE,
    validation_errors TEXT,
    raw_message JSONB
);
