FROM python:3.9-slim-buster

# Create default user folder
RUN mkdir -p /home/pi

RUN apt update && apt install -y nano screen

COPY install-necessary-stuff.sh /
RUN ./install-necessary-stuff.sh


COPY services /home/pi/services
RUN cd /home/pi/services && pip3 install .

ENTRYPOINT /home/pi/services/run.sh && sleep infinity
