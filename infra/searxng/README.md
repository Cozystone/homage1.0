# ATANOR SearXNG (self-hosted metasearch)
open-web intake PRIMARY source (web_search.py: searxng_search, SEARXNG_URL=http://127.0.0.1:8888).
run:  MSYS_NO_PATHCONV=1 docker run -d --name atanor-searxng --restart unless-stopped -p 8888:8080 -v "C:/0.ASKIM ALL-VIN/27., ATANOR DEMO/infra/searxng:/etc/searxng" searxng/searxng
NOTE: git-bash mangles /etc/searxng without MSYS_NO_PATHCONV=1 (mount silently fails, json 403).
settings.yml enables format=json (required); secret_key is machine-local — regenerate if cloned.
