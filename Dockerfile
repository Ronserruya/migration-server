FROM python:3.7-stretch

# Create the workdir
RUN mkdir -p /opt/app

# Set the workdir
WORKDIR /opt/app

# Copy the pipfiles
COPY Pipfile* ./

# Install dependencies
RUN pip install pipenv==2018.10.13 \
    &&  pipenv install

# Copy the code
COPY . .

# Run with gunicorn thread workers (2 x $num_cores) + 1 according to gunicorn docs recommendation
CMD pipenv run gunicorn --threads=$(expr 2 \* $(nproc) + 1) -b 0.0.0.0 -p 8000 src.app:app
