# Deployment Checklist

## Purpose

This checklist guides a non-technical user through deploying the `exr-inspector` DataEngine function.

## Prerequisites

- VAST DataEngine CLI installed (admin can assist).
- Access to a container registry connected to the VAST tenant.
- Permission to create functions and pipelines in the VAST UI.
- Screenshot placeholders captured (optional).

## Fill-In Details

- Registry host: `_______________________________`
- Artifact source/path: `_______________________________`
- Image tag: `_______________________________`
- Function name in VAST UI: `_______________________________`
- Pipeline name: `_______________________________`

## Build & Package

- [ ] Create a local functions folder (example: `~/functions/`).
- [ ] Create a function scaffold:

```
vastde functions init python-pip exr_inspector -t ~/functions/
```

- [ ] Copy the repo folder `functions/exr_inspector/` into `~/functions/exr_inspector/`.
- [ ] Build the container image:

```
vastde functions build exr-inspector -target ~/functions/exr_inspector --image-tag exr-inspector
```

## Test (Optional)

- [ ] Start a local function container:

```
vastde functions localrun
```

- [ ] Invoke the function with a sample event:

```
vastde functions invoke
```

## Push to Registry

- [ ] Tag the image:

```
docker tag exr-inspector:latest CONTAINER_REGISTRY/ARTIFACT_SOURCE:TAG
```

- [ ] Push the image:

```
docker push CONTAINER_REGISTRY/ARTIFACT_SOURCE:TAG
```

## Create Function in VAST UI

- [ ] Navigate to **Manage Elements → Functions**.
- [ ] Click **Create New Function**.
- [ ] Provide:
  - Name
  - Description
  - Revision alias/description
  - Container registry
  - Artifact source
  - Image tag
- [ ] Click **Create Function**.

Screenshot placeholders:

- [ ] `docs/screenshots/vast-functions-list.png`
- [ ] `docs/screenshots/vast-function-create.png`

## Deploy in Pipeline

- [ ] Add the function to a DataEngine pipeline.
- [ ] Connect a trigger (file/object update) to the function.
- [ ] Deploy the pipeline.

Screenshot placeholders:

- [ ] `docs/screenshots/vast-pipeline-editor.png`
- [ ] `docs/screenshots/vast-trigger-config.png`

## Verification

- [ ] Trigger on a known EXR file.
- [ ] Confirm output JSON is produced.
- [ ] Confirm VAST DataBase entries (if configured).

Screenshot placeholders:

- [ ] `docs/screenshots/vast-run-history.png`

## Notes

- For VAST DataBase persistence, ensure env vars are set:
  - `VAST_DB_HOST`
  - `VAST_DB_USER`
  - `VAST_DB_PASSWORD`
  - `VAST_DB_NAME`
