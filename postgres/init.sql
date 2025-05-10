-- Crear la tabla para los logs meteorológicos si no existe
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
    validation_errors TEXT, -- Para almacenar errores de validación
    raw_message JSONB      -- Para almacenar el mensaje original si es inválido o para auditoría
);

-- Crear índices para consultas comunes (opcional pero recomendado)
CREATE INDEX IF NOT EXISTS idx_weather_logs_timestamp ON weather_logs (timestamp);
CREATE INDEX IF NOT EXISTS idx_weather_logs_station_id ON weather_logs (station_id);
CREATE INDEX IF NOT EXISTS idx_weather_logs_is_valid ON weather_logs (is_valid);

-- Otorgar privilegios al usuario de la aplicación (si no se hizo a nivel de DB)
-- Esto usualmente se maneja con las variables de entorno de la imagen de Postgres
-- GRANT ALL PRIVILEGES ON TABLE weather_logs TO weatheruser;
-- GRANT USAGE, SELECT ON SEQUENCE weather_logs_id_seq TO weatheruser;

-- Comentario: La base de datos y el usuario serán creados por las variables de entorno
-- en docker-compose.yml. Este script se ejecutará dentro de esa base de datos.