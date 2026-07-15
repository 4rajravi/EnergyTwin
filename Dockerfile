FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY run.py ./

RUN python -m pip install --no-cache-dir 'psycopg[binary]>=3.2' 'redis>=5.0'

ENV PYTHONPATH=/app/src
ENV ENERGYTWIN_HOST=0.0.0.0
ENV ENERGYTWIN_PORT=8787

EXPOSE 8787

CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8787"]
