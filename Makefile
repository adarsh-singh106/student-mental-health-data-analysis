# Short names for the long docker commands, so a stranger (or you, in two
# months) can run this project without memorising anything.
#
#   make build   build the image once (recipe -> blueprint)
#   make train   train the model inside a container (writes to ./artifacts)
#   make serve   serve the API on http://localhost:8000
#   make test    run the test suite
#
# Data (./data) and models (./artifacts) are mounted from the host, never baked
# into the image (Raasta B).

IMAGE := mental-health

# These names are commands, not files, so declare them "phony" (make should
# always run them, never look for a file called "build"/"train"/etc).
.PHONY: build train serve test

build:
	docker build -t $(IMAGE) .

# Mount ./data (read-only: training only reads the CSV) and ./artifacts
# (writable: the trained model is written back out to the host).
train: build
	docker run --rm \
		-v "$(CURDIR)/data:/app/data:ro" \
		-v "$(CURDIR)/artifacts:/app/artifacts" \
		$(IMAGE) python -m mental_health.models.train

# Mount ./artifacts read-only (serving only reads the model). -p maps the
# container's port 8000 to your laptop's 8000 so a browser can reach it.
serve: build
	docker run --rm \
		-p 8000:8000 \
		-v "$(CURDIR)/artifacts:/app/artifacts:ro" \
		$(IMAGE)

# Tests are copied into the image and dev deps (pytest/httpx) are installed by
# `uv sync`, so no mounts and no extra flags are needed — just run pytest.
test: build
	docker run --rm $(IMAGE) pytest
