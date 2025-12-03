# Using an official Python Debian image as a baseline
# https://hub.docker.com/_/python
# https://www.debian.org/releases/
#
# NOTE: Not supporting Windows because uWSGI requires additional steps for Windows installation
# NOTE: Also when using the slim variant, some more dependencies need to be installed (uWSGI compiles with gcc)
FROM python:3.13-slim

ARG GAME_GIT_HASH
ENV GAME_GIT_HASH=$GAME_GIT_HASH
ARG GAME_GIT_HASH_SHORT
ENV GAME_GIT_HASH_SHORT=$GAME_GIT_HASH_SHORT

ARG PROMETHEUS_MULTIPROC_DIR="/tmp/prometheus_multiproc"

# Labels as per:
# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
MAINTAINER Max Planck Institute for Security and Privacy
LABEL org.opencontainers.image.authors="Max Planck Institute for Security and Privacy"
# NOTE Also change the version in config.py
LABEL org.opencontainers.image.version="2.1.0"
LABEL org.opencontainers.image.licenses="AGPL-3.0-only"
LABEL org.opencontainers.image.description="Ready to deploy Docker container to use ReverSim for research. ReverSim is an open-source environment for the browser, originally developed at the Max Planck Institute for Security and Privacy (MPI-SP) to study human aspects in hardware reverse engineering."
LABEL org.opencontainers.image.source="https://github.com/emsec/ReverSim"

# When using the slim variant, a toolchain is needed to compile uWSGI
# Yeet the apt-cache afterwards, since it is no longer needed
RUN apt-get update && apt-get install -y gcc nano htop && rm -rf /var/lib/apt/lists/*

# Create a non root user for enhanced security
RUN groupadd -r uwsgi && useradd -r -g uwsgi uwsgi

# Change workdir to folder where the game will be installed (affects COPY, RUN etc.)
WORKDIR /usr/src/hregame

# Install all Python libs that are required (installing under the root user, since the other user has no home)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set the ownership and permissions for the application files, switch to this user for the rest of the script
RUN chown -R uwsgi:uwsgi /usr/src/hregame && mkdir /var/log/uwsgi && chown -R uwsgi:uwsgi /var/log/uwsgi
USER uwsgi

# Copy the game code
COPY app app/
COPY static static/
COPY templates templates/
COPY migrations migrations/
COPY gameServer.py gameServer.py
COPY --chmod=755 docker-entrypoint.sh docker-entrypoint.sh

# Copy the examples config & assets folder and make it the default one
ENV REVERSIM_INSTANCE="/usr/var/reversim-instance"
WORKDIR /usr/var/reversim-instance
COPY examples/conf conf
COPY instance/conf conf

# Setup for Prometheus multiprocessing
WORKDIR ${PROMETHEUS_MULTIPROC_DIR}
ENV PROMETHEUS_MULTIPROC_DIR=${PROMETHEUS_MULTIPROC_DIR}

# Create empty statistics folders
WORKDIR /usr/var/reversim-instance/statistics/LogFiles
WORKDIR /usr/var/reversim-instance/statistics/canvasPics
WORKDIR /usr/src/hregame

# Specify mount points for the statistics folder, levels, researchInfo & disclaimer
VOLUME /usr/var/reversim-instance/statistics
VOLUME /var/log/uwsgi

# Exposes the port that uWSGI is listening to (as configured in hre_game.ini)
EXPOSE 8000

# Run the uWSGI server when the container launches
CMD ["/usr/src/hregame/docker-entrypoint.sh"]
