# exr-inspector DataEngine Function

This is the VAST DataEngine serverless Python function scaffold for exr-inspector.

## Build (DataEngine CLI)

```
vastde functions build exr-inspector -target /path/to/functions/exr_inspector --image-tag exr-inspector
```

## Quick Start (Non-Technical)

1) Install the VAST DataEngine CLI (ask your admin if needed).
2) Create a folder on your machine, for example: `~/functions/`.
3) Run this command to create a function scaffold (you can reuse this repo’s folder instead):

```
vastde functions init python-pip exr_inspector -t ~/functions/
```

4) Copy this folder (`functions/exr_inspector/`) into the scaffold path:
   `~/functions/exr_inspector/`
5) Build the container image:

```
vastde functions build exr-inspector -target ~/functions/exr_inspector --image-tag exr-inspector
```

6) Test locally:

```
vastde functions localrun
vastde functions invoke
```

7) Tag and push the image to your registry:

```
docker tag exr-inspector:latest CONTAINER_REGISTRY/ARTIFACT_SOURCE:TAG
docker push CONTAINER_REGISTRY/ARTIFACT_SOURCE:TAG
```

8) In the VAST UI: Manage Elements → Functions → Create New Function.
   - Pick the container registry, artifact source, and image tag you pushed.
   - Create the function.

9) Add the function to a DataEngine pipeline and connect it to a trigger.

## Local Test

```
vastde functions localrun
vastde functions invoke
```

## Notes

- The handler expects an event with a file path.
- EXR parsing uses OpenImageIO when available in the runtime image.
