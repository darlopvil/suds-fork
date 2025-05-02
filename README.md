# Suds
Suds is a privacy-respecting frontend to Snopes.com

# Instances
See instances.json

# Support
Join our [Matrix room](https://mto.vern.cc/#/#cobra-frontends:vern.cc) for support and other things related to Suds

# Run your own instance
## Dependencies
This program depends on `bs4`, `requests`, and `flask`. Install them by running `pip3 install bs4 requests flask`.

For the production environment, you also need the uWSGI Python3 plugin. On Debian, it can be installed via `apt install uwsgi-plugin-python3`
## Production
1. Clone the repository
2. Run `uwsgi --plugin python3 --http-socket 0.0.0.0:8001 --wsgi-file main.py --callable app --processes 4 --threads 2`
3. Point your reverse proxy to http://localhost:8001
## Development
1. Clone the repository
2. Run `python3 main.py`
3. Connect to http://localhost:8001
