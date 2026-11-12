# Third-party models

Every learned model Orrery uses, with its source, version, and license. Weights are downloaded when images are built and are never committed to this repository.

No model is integrated yet. The table lists the models chosen in `.kiro/steering/tech.md`. Each row gains its exact checkpoint, ONNX export, and checksum when the feature that uses it ships.

| Model                         | Used for                                               | Runs in                         | Source                                 | Version  | License                                         | Integrated |
| ----------------------------- | ------------------------------------------------------ | ------------------------------- | -------------------------------------- | -------- | ----------------------------------------------- | ---------- |
| SAM 2.1 (tiny or small)       | Interactive part outlining                             | Browser (transformers.js, ONNX) | Meta AI, `facebookresearch/sam2`       | 2.1      | Apache-2.0                                      | No         |
| DINOv2 ViT-S/14               | Part re-identification between footage                 | Engine (ONNX Runtime, CPU)      | Meta AI, `facebookresearch/dinov2`     | ViT-S/14 | Apache-2.0                                      | No         |
| CoTracker3 (optional backend) | Point tracking, only if the lab benchmark justifies it | Engine (ONNX Runtime, CPU)      | Meta AI, `facebookresearch/co-tracker` | 3        | CC-BY-NC 4.0 (weights): non-commercial use only | No         |
