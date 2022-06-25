FROM python:3.9-slim-bullseye

# Create default user folder
RUN mkdir -p /home/pi

# Install some useful tools
RUN apt update && apt install -y --no-install-recommends \
    curl \
    dnsutils \
    file \
    htop \
    iproute2 \
    iputils-ping \
    less \
    lsof \
    nano \
    rsync \
    screen \
    tree


# Install stuff necessary to run the scripts
COPY install-necessary-stuff.sh /
RUN ./install-necessary-stuff.sh


COPY services /home/pi/services
RUN cd /home/pi/services && pip3 install .

ENTRYPOINT /home/pi/services/run.sh && sleep infinity
