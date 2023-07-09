# Use an official Python runtime as a parent image
FROM python:3.10-slim as base

# Set the working directory to /app
WORKDIR /hover-dns-updater

# Copy the current directory contents into the container at /app
ADD hover-dns-updater.py hover-update.cfg requirements.txt /hover-dns-updater/

# Install any needed packages specified in requirements.txt
RUN pip install -U pip && \
    pip install -r requirements.txt

# Define environment variable
ENV NAME hover-dns-updater

FROM base as test
ADD requirements-dev.txt /hover-dns-updater/
RUN pip install -r requirements-dev.txt && \
    pytest hover-dns-updater.py

FROM base as production
# Run app.py when the container launches
CMD ["python", "hover-dns-updater.py", "--service"]


