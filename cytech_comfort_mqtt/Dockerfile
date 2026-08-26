ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk update --no-cache && apk upgrade --no-cache

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        paho-mqtt \
        cryptography \
        requests \
        defusedxml \
        pyserial \
        flask \
        werkzeug

# Copy root filesystem
COPY rootfs /

# Ensure s6 scripts are executable
RUN chmod +x /etc/services.d/cytech_comfort_mqtt/run \
 && chmod 755 /etc/services.d/cytech_comfort_mqtt/finish \
 && chmod +x /etc/services.d/cytech_comfort_web/run