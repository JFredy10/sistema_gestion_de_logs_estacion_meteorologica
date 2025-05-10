# Usar una imagen base de Python 3.13+
FROM python:3.13-slim

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar el archivo de requerimientos e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY producer.py .

# Comando para ejecutar la aplicación
CMD ["python", "producer.py"]