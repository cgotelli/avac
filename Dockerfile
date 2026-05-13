FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends gfortran make git libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-gui.txt /app/requirements-gui.txt
RUN python -m pip install --no-cache-dir -r requirements-gui.txt

COPY . /app

ENV QT_QPA_PLATFORM=offscreen
CMD ["python", "avac_gui.py"]
