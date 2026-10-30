# R1 OCR corpus evaluation

`scripts/evaluate_ocr_dataset.py` supplies a bounded opt-in evaluation harness for R1-06. It uses the existing real `OCRSandbox`: no network, host mounts, daemon logs or credentials inside inference. This adds no production enablement, automatic employee approval or identity document retention changes.

An authorized operator prepares a private local directory containing PNG/JPEG images and a UTF-8 JSON manifest:

```json
[
  {
    "image": "fictional-example.png",
    "expected_name": "Synthetic Tester",
    "expected_employee_id": "MESH-TEST-42"
  }
]
```

Both expected fields are required; use null where the image contains no corresponding field. Use only approved ground truth; do not commit representative identity images or manifests. Paths must resolve inside the manifest directory, be relative and unique. The manifest is capped at 1 MiB/1,000 entries, each image at 2 MiB, and total input at 64 MiB. Existing image decoding/signature/dimension validation runs before daemon submission. A failure returns a sanitized failure status without sample paths, expected identities or engine exceptions. No partial success report is emitted.

Invocation from the backend root:

```text
python scripts/evaluate_ocr_dataset.py --manifest <private-manifest-path> --docker-executable <absolute-trusted-docker-path> --image <local-repository>@sha256:<approved-digest> --authorized-dataset
```

The explicit authorization flag is an operator attestation, not an automated privacy approval. A locally present immutable image is mandatory: either a repository `@sha256:` manifest reference or an exact local `sha256:` image ID. Mutable tags are rejected, and a local image ID must match the daemon's inspected ID exactly. This supports isolated local builds without publishing an image to a registry. The harness does not pull images. Docker availability and runtime clearance must be established separately. Standard output contains only aggregate counts/accuracy and the executed image identity/reference; redirect to an approved report location if needed. Expected and predicted names/IDs are not emitted or persisted by the harness. Ground-truth material remains private in the operator corpus.

Per-field results distinguish exact matches, normalized matches, abstentions, incorrect nonempty extractions and expected-present counts. Accuracy denominator is the complete corpus, including known-absent fields. Normalization is Unicode NFKC, case folding and whitespace only: punctuation in employee IDs is preserved, so `ID-1` does not equal `ID1`. Review exact and normalized metrics together; absent fields and a skewed corpus can inflate aggregate accuracy. There are no invented confidence scores, automatic pass thresholds or representativeness claims.

Unit tests verify aggregation/redaction, authorization gating, corpus bounds, invalid expected values, duplicate paths and traversal rejection. The harness has not been run against a representative authorized corpus: none is configured. Existing isolated fictional-image engine acceptance remains separate evidence. Organization-approved sampling, quality thresholds, demographic/language/document coverage, privacy/access/retention procedures, independent HR review, image/advisory clearance, malware-definition updates and deployed worker/encryption-key handling remain necessary for production R1-06 acceptance.
