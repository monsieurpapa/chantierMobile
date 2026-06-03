FROM python:3.12-alpine

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apk update \
    && apk add --no-cache postgresql-dev gcc python3-dev musl-dev gettext

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && python manage.py collectstatic --no-input && gunicorn chantiermobile.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120"]
