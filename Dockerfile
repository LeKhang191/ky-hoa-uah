FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh", "-c", "flask --app app init-db && gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 'app:create_app()'"]
