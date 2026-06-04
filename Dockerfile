FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY order_dashboard ./order_dashboard
# vi_export_generator is vendored from the sibling repo (dependency-free, pure
# stdlib). The dashboard imports it to build the Visual Integrator CSV on submit.
COPY vi_export_generator ./vi_export_generator
COPY seed.py .

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--access-logfile", "-", "order_dashboard:create_app()"]
