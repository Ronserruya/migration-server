FROM python:3.7-stretch

# Create the workdir
RUN mkdir -p /opt/app

# Set the workdir
WORKDIR /opt/app

# Copy the pipfiles
COPY Pipfile* ./

# Install dependencies
RUN pip install pipenv==2018.11.26
RUN pipenv install

# Copy the code
COPY . .

# Run with gunicorn thread workers (2 x $num_cores) + 1 according to gunicorn docs recommendation
CMD pipenv run gunicorn --worker-class=gevent --worker-connections=1000 --workers=$(expr 2 \* $(nproc) + 1) -b 0.0.0.0:8000 src.app:app
