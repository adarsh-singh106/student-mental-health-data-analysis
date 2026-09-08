# Short names for the commands, so a stranger (or you in two months) can run
# this project without memorising anything.
#
#   make train   train the model on the HOST (writes ./artifacts)
#   make test    run the tests on the HOST
#   make build   build the serving image (recipe -> blueprint)
#   make serve   serve the API from the container on http://localhost:8000
#
# Why the split: training records the git commit into the model's metadata
# (provenance — see save.py), and a clean git repo only exists on the host; the
# image deliberately ships no .git. So training and dev tests run on the host
# via uv, and the container is the deployable that serves the trained model.
# (CI additionally builds the image and runs pytest inside it — .github/workflows.)

IMAGE := mental-health
DATA_PATH ?= $(CURDIR)/data/raw/Student Social Media And Mental Health Impact.csv
ARTIFACTS_ROOT ?= $(CURDIR)/artifacts

.PHONY: train test build serve

# Host: needs an explicit data path (see scripts/fetch_data.py) and a clean Git
# tree. The release CLI records both the input hash and an artifact manifest.
# Override either path without editing source, for example:
#   make train DATA_PATH="C:/data/input.csv" ARTIFACTS_ROOT="C:/releases"
train:
	uv run --frozen python -m mental_health.models.release --data-path "$(DATA_PATH)" --artifacts-root "$(ARTIFACTS_ROOT)"

test:
	uv run --frozen pytest

build:
	docker build -t $(IMAGE) .

# Mount the host's ./artifacts read-only so the container serves the trained
# model. -p maps the container's port 8000 to your laptop's 8000.
serve: build
	docker run --rm \
		-p 8000:8000 \
		-v "$(ARTIFACTS_ROOT):/app/artifacts:ro" \
		$(IMAGE)
