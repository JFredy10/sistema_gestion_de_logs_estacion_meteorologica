import pika
import json
import time
import random
from datetime import datetime
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'password')
EXCHANGE_NAME = 'weather_exchange'
ROUTING_KEY = 'weather.data'

def generate_weather_data(station_id="station_01"):
    """Genera datos simulados de una estación meteorológica."""
    timestamp = datetime.now().isoformat()
    temperature = round(random.uniform(-10.0, 45.0), 2) # Celsius
    humidity = round(random.uniform(20.0, 100.0), 2)    # Percent
    pressure = round(random.uniform(980.0, 1050.0), 2)  # hPa
    wind_speed = round(random.uniform(0.0, 100.0), 2)   # km/h
    # Simular posibilidad de valores fuera de rango o erróneos para probar la validación
    if random.random() < 0.05: # 5% de probabilidad de temperatura anómala
        temperature = round(random.uniform(70.0, 100.0), 2)
    if random.random() < 0.03: # 3% de probabilidad de datos faltantes (simulado como None)
        humidity = None

    data = {
        "station_id": station_id,
        "timestamp": timestamp,
        "temperature_celsius": temperature,
        "humidity_percent": humidity,
        "pressure_hpa": pressure,
        "wind_speed_kmh": wind_speed
    }
    return data

def connect_rabbitmq():
    """Establece conexión con RabbitMQ."""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, credentials=credentials, heartbeat=600, blocked_connection_timeout=300)
    retry_interval = 5
    while True:
        try:
            connection = pika.BlockingConnection(parameters)
            logging.info("Productor conectado a RabbitMQ.")
            return connection
        except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError) as e:
            logging.error(f"Error conectando a RabbitMQ: {e}. Reintentando en {retry_interval} segundos...")
            time.sleep(retry_interval)

def main():
    connection = connect_rabbitmq()
    channel = connection.channel()

    # Declarar el exchange como durable
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='direct', durable=True)
    logging.info(f"Exchange '{EXCHANGE_NAME}' declarado.")

    try:
        while True:
            weather_data = generate_weather_data()
            message_body = json.dumps(weather_data, default=str) # default=str para manejar datetime si no es isoformat

            channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=ROUTING_KEY,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE # Mensajes persistentes
                )
            )
            logging.info(f"Enviado: {message_body}")
            time.sleep(random.randint(2, 7)) # Simular envíos a intervalos variables
    except KeyboardInterrupt:
        logging.info("Productor detenido por el usuario.")
    except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError) as e:
        logging.error(f"Error de conexión con RabbitMQ en el bucle principal: {e}")
        # Idealmente, aquí se reintentaría la conexión y la publicación
    finally:
        if connection and not connection.is_closed:
            connection.close()
            logging.info("Conexión de RabbitMQ cerrada.")

if __name__ == '__main__':
    main()