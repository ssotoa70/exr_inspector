# VAST Integration Notes

## Scope

This document captures the intended integration of `exr-inspector` with VAST DataEngine and VAST DataBase. It is based on publicly available product pages and the official VAST DataEngine User Guide.

## DataEngine Compatibility

- Deploy as a serverless Python function.
- Expect stateless execution in containers located near the data.
- Use event-driven triggers tied to file/object updates to initiate inspection runs.
- Avoid data movement; read EXR content in-place.
- Enforce streaming reads; no full image loads unless explicitly requested.

## Creating a DataEngine Function (Guide Excerpt)

The VAST DataEngine user guide describes a function as a resource that points to a container image stored in a connected container registry. Functions are packaged as images via the DataEngine CLI, then referenced in pipelines by revision.

Workflow:

1. Prepare the function image in the container registry.
2. Create the function resource in DataEngine.

Prepare the function image:

- Install the VAST DataEngine CLI.
- Initialize a function scaffold:

```
vastde functions init python-pip my_first_function -t ~/functions/
```

- Scaffold includes: `Aptfile`, `README.md`, `customDeps`, `main.py`, `requirements.txt`.
- Implement function code in `main.py` (see Runtime SDK Guide).
- Build the container image:

```
FUNC_NAME="function"
FUNC_PATH="example/path/to/function"
vastde functions build $FUNC_NAME -target $FUNC_PATH --image-tag my-function
```

- Test locally:
  - `vastde functions localrun`
  - `vastde functions invoke`
- Tag and push the image:

```
docker tag ${FUNC_NAME}:latest CONTAINER_REGISTRY/ARTIFACT_SOURCE:TAG
docker push CONTAINER_REGISTRY/ARTIFACT_SOURCE:${FUNC_NAME}
```

Create the function resource:

- In DataEngine UI: Manage Elements → Functions → Create New Function.
- Provide name, description, revision alias/description, and image fields:
  - Container Registry
  - Artifact Source
  - Image Tag
  - Full image path (auto-formed)
- Create the function; it becomes available for pipelines and triggers.

## DataBase Persistence

- Store extracted metadata, optional stats, and validation results in VAST DataBase.
- Use transactional writes for consistency and auditing.
- Support analytical queries over structured EXR metadata for pipeline and AI workflows.
- Prefer idempotent writes (upsert) keyed on file path + mtime + hash (final key to be confirmed).

## Data Model (Draft)

- `files`
  - `path` (string, primary identifier)
  - `size_bytes` (int)
  - `mtime` (timestamp)
  - `exr_version` (string)
  - `multipart_count` (int)
  - `is_deep` (bool)
  - `hash` (string, optional)
- `parts`
  - `file_path` (string, FK)
  - `part_index` (int)
  - `part_name` (string)
  - `view_name` (string)
  - `data_window` (json)
  - `display_window` (json)
  - `pixel_aspect_ratio` (float)
  - `line_order` (string)
  - `compression` (string)
  - `tiling` (json)
- `channels`
  - `file_path` (string, FK)
  - `part_index` (int)
  - `name` (string)
  - `type` (string)
  - `x_sampling` (int)
  - `y_sampling` (int)
  - `linearity` (string, nullable)
- `attributes`
  - `file_path` (string, FK)
  - `part_index` (int, nullable)
  - `name` (string)
  - `type` (string)
  - `value` (json)
- `stats`
  - `file_path` (string, FK)
  - `part_index` (int)
  - `channel` (string)
  - `min` (float)
  - `max` (float)
  - `mean` (float)
  - `stddev` (float)
  - `nan_count` (int)
  - `inf_count` (int)
  - `sample_stride` (int)
- `validation`
  - `file_path` (string, FK)
  - `code` (string)
  - `severity` (string)
  - `message` (string)

## Open Questions

- Final trigger/event payload for DataEngine functions.
- Authentication and connection mechanism to VAST DataBase.
- Preferred schema (single wide table vs normalized tables).
- Required indices for common queries.
- Retention policy for historical runs.
