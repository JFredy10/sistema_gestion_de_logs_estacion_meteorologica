import pika
import json
import time
import psycopg2
from psycopg2 import pool
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# RabbitMQ Config
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'password')
EXCHANGE_NAME = 'weather_exchange'
QUEUE_NAME = 'weather_log_queue'
ROUTING_KEY = 'weather.data' # Debe coincidir con el productor

# PostgreSQL Config
DB_HOST = os.getenv('DB_HOST', 'postgres')
DB_NAME = os.getenv('DB_NAME', 'weatherdb')
DB_USER = os.getenv('DB_USER', 'weatheruser')
DB_PASS = os.getenv('DB_PASS', 'weatherpass')

# Pool de conexiones a PostgreSQL
db_pool = None

def init_db_pool():
    global db_pool
    while True:
        try:
            logging.info(f"Intentando conectar a PostgreSQL en {DB_HOST}...")
            db_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=5, # Ajustar según sea necesario
                user=DB_USER,
                password=DB_PASS,
                host=DB_HOST,
                port="5432",
                database=DB_NAME
            )
            conn = db_pool.getconn()
            conn.autocommit = True # Para la creación de tabla si no existe
            cur = conn.cursor()
            # Verificar si la tabla existe (opcional, init.sql debería manejar esto)
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'weather_logs'
                );
            """)
            if not cur.fetchone()[0]:
                logging.warning("La tabla 'weather_logs' no existe. Asegúrate que init.sql se haya ejecutado.")
                # Podrías intentar crearla aquí como fallback, pero es mejor que init.sql lo haga.
            cur.close()
            db_pool.putconn(conn)
            logging.info("Pool de conexiones a PostgreSQL inicializado.")
            break
        except psycopg2.OperationalError as e:
            logging.error(f"Error conectando a PostgreSQL: {e}. Reintentando en 5 segundos...")
            time.sleep(5)

def validate_data(data):
    """Valida los rangos de los datos meteorológicos."""
    errors = []
    temp = data.get("temperature_celsius")
    humidity = data.get("humidity_percent")
    pressure = data.get("pressure_hpa")
    wind = data.get("wind_speed_kmh")

    if temp is not None and not (-70 <= temp <= 70): # Rango amplio para climas extremos
        errors.append(f"Temperatura fuera de rango: {temp}°C")
    if humidity is not None and not (0 <= humidity <= 100):
        errors.append(f"Humedad fuera de rango: {humidity}%")
    if pressure is not None and not (800 <= pressure <= 1100):
        errors.append(f"Presión fuera de rango: {pressure} hPa")
    if wind is not None and not (0 <= wind <= 400): # ~velocidad de un tornado F5
        errors.append(f"Velocidad del viento fuera de rango: {wind} km/h")

    # Verificar campos obligatorios (timestamp y station_id deberían estar siempre por diseño del productor)
    if not data.get("station_id"):
        errors.append("Falta station_id")
    if not data.get("timestamp"):
        errors.append("Falta timestamp")

    return not errors, errors

def persist_data(data):
    """Persiste los datos en PostgreSQL."""
    is_valid, validation_errors = validate_data(data)
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            if is_valid:
                cur.execute("""
                    INSERT INTO weather_logs (station_id, timestamp, temperature_celsius, humidity_percent, pressure_hpa, wind_speed_kmh, is_valid, validation_errors)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    data.get("station_id"),
                    data.get("timestamp"),
                    data.get("temperature_celsius"),
                    data.get("humidity_percent"),
                    data.get("pressure_hpa"),
                    data.get("wind_speed_kmh"),
                    True,
                    None
                ))
                conn.commit()
                logging.info(f"Datos válidos persistidos para {data.get('station_id')}: temp {data.get('temperature_celsius')}")
            else:
                error_message = ", ".join(validation_errors)
                cur.execute("""
                    INSERT INTO weather_logs (station_id, timestamp, temperature_celsius, humidity_percent, pressure_hpa, wind_speed_kmh, is_valid, validation_errors, raw_message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    data.get("station_id"),
                    data.get("timestamp"),
                    data.get("temperature_celsius"), # Guardar el valor aunque esté mal para análisis
                    data.get("humidity_percent"),
                    data.get("pressure_hpa"),
                    data.get("wind_speed_kmh"),
                    False,
                    error_message,
                    json.dumps(data) # Guardar el mensaje original
                ))
                conn.commit()
                logging.warning(f"Datos inválidos para {data.get('station_id')}: {error_message}. Mensaje original: {data}")
        return True
    except (Exception, psycopg2.Error) as error:
        if conn:
            conn.rollback() # Importante si no se usa autocommit en la conexión principal
        logging.error(f"Error al persistir datos: {error}")
        # Considerar una cola de reintentos o "dead letter queue" para fallos de DB
        return False
    finally:
        if conn:
            db_pool.putconn(conn)


def on_message_callback(ch, method, properties, body):
    """Procesa el mensaje recibido."""
    try:
        logging.info(f"Recibido mensaje: {body.decode()[:100]}...") # Loguear solo una parte
        message_data = json.loads(body.decode())

        if persist_data(message_data):
            ch.basic_ack(delivery_tag=method.delivery_tag) # Confirmación manual
            logging.info("Mensaje procesado y confirmado (ACK).")
        else:
            # Aquí decides qué hacer con el mensaje si la persistencia falla
            # Opciones:
            # 1. Rechazar y no reencolar (si el error es por el mensaje y no se puede procesar)
            # ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            # 2. Rechazar y reencolar (si el error es temporal, ej. DB no disponible por un momento)
            # ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            # Por ahora, si hay un error grave en persist_data (ej. DB Pool no disponible por mucho tiempo)
            # el script podría fallar y Docker lo reiniciaría.
            # Si persist_data devuelve False por un error de SQL que no es de conexión,
            # lo ideal sería moverlo a una dead-letter queue.
            # Para este ejemplo, si persist_data Falla (no por validación, sino error DB), se loguea y se hace NACK sin reencolar.
            logging.error(f"Fallo crítico al persistir, mensaje no será reencolado. DLQ sería útil aquí. Tag: {method.delivery_tag}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Evitar bucles infinitos de error

    except json.JSONDecodeError as e:
        logging.error(f"Error decodificando JSON: {e}. Mensaje: {body.decode()}")
        ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False) # Mensaje malformado, no reencolar
    except Exception as e:
        logging.error(f"Error inesperado procesando mensaje: {e}")
        # Decidir si reencolar o no basado en la naturaleza del error.
        # Por seguridad, no reencolar para evitar bucles.
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def connect_rabbitmq_consumer():
    """Establece conexión con RabbitMQ para el consumidor."""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, credentials=credentials, heartbeat=600, blocked_connection_timeout=300)
    retry_interval = 5
    while True:
        try:
            connection = pika.BlockingConnection(parameters)
            logging.info("Consumidor conectado a RabbitMQ.")
            return connection
        except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError) as e:
            logging.error(f"Error conectando consumidor a RabbitMQ: {e}. Reintentando en {retry_interval} segundos...")
            time.sleep(retry_interval)


def main():
    init_db_pool() # Inicializar el pool de DB antes de consumir

    connection = connect_rabbitmq_consumer()
    channel = connection.channel()

    # Declarar el exchange (debe coincidir con el productor)
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='direct', durable=True)
    logging.info(f"Exchange '{EXCHANGE_NAME}' verificado/declarado.")

    # Declarar la cola como durable
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    logging.info(f"Cola '{QUEUE_NAME}' declarada.")

    # Vincular la cola al exchange
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=ROUTING_KEY)
    logging.info(f"Cola '{QUEUE_NAME}' vinculada al exchange '{EXCHANGE_NAME}' con routing key '{ROUTING_KEY}'.")

    # Consumir con prefetch_count=1 para procesamiento ordenado y ack manual
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message_callback, auto_ack=False) # auto_ack=False para ack manual

    logging.info("Consumidor esperando mensajes. Para salir presione CTRL+C")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logging.info("Consumidor detenido por el usuario.")
    except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError) as e:
        logging.error(f"Error de conexión con RabbitMQ durante el consumo: {e}")
        # Aquí se podría implementar una lógica de reconexión más robusta para el canal.
    finally:
        if connection and not connection.is_closed:
            connection.close()
            logging.info("Conexión de RabbitMQ del consumidor cerrada.")
        if db_pool:
            db_pool.closeall()
            logging.info("Pool de conexiones a PostgreSQL cerrado.")

if __name__ == '__main__':
    main()