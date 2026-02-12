# Worker_Engraving_Spec.md

## Scope
Generate renderable notation outputs (MusicXML to PDF/PNG) and maintain export fidelity.

## Responsibilities
- Accept MusicXML and layout options.
- Produce print-quality PDF and preview-quality PNG.
- Validate output readability constraints.

## Quality Gates
- Output artifact checks for existence, page count, and non-empty render.
- Error messaging for invalid or incomplete score inputs.
