# Prompt Completeness Checklist (prompt-checklist)

> Purpose: check the prompt section by section before generating. If any section is missing, fill it in before moving to parameter confirmation.
> Root cause: constraints settled in conversation are not remembered for you by the model or by future sessions — an omission becomes a generation accident.

## Eight-section structure

1. **Asset-domain declaration**: character or scene, single panorama or composite image, what environment is excluded.
2. **Subject description**: grounded features of this subject (**only when there is no reference image**); **when there is a reference image, write no shape description at all** (see "Two prompt disciplines" below), keeping only state changes the reference image cannot cover (e.g. opening state).
3. **Aspect-ratio lock section**: convert settled aspect-ratio data into compositional language — **shape words first** (near-square, wide horizontal rectangle), with multiples and frame share as fallback (total width about N times total height; the top of the head falls at N% of the door height), plus a reverse exclusion (must not be drawn ant-sized).
4. **Structure and opening-mechanism section**: movable structures must explicitly state the motion (horizontal translation/rotation/vertical lift...), and give counter-example prohibitions (does not rotate, does not pivot, does not swing outward, does not lift up). **Historical accident: omitting the opening mechanism leads to repeated generations of a wrong movable structure — record the pitfalls your project has hit in the "structure and opening mechanism" section of the project record.**
5. **Art-style section**: **decide per scene whether it is mandatory** —
   - **Mandatory**: generating from scratch / repaint-style upscaling (HD enhancement) / changing pose or appearance / multi-image composite repaint. All four make the model repaint, so if the art style is not pinned it drifts.
   - **Optional**: pure mask local repaint, and slight edits that change only one small spot — the base image carries its own art style, the change scope is small, and drift risk is low.
   Write only **rendering language + lighting and saturation tone + negative**; the concrete template comes from the "art style" section of the project record `.image-generation/profile.md` (example in `references/profile.example.md`); with no record, draft it yourself from these three elements.
   **Material is not written in this section**: material varies per asset, so write it into each asset's own prompt (this section defines only rendering language; listing materials is bound to miss some).
   **No unified color card**: color follows the tone of the reference image / existing assets (different scenes / assets in one project each have their own tone; unifying them distorts).
6. **Layout**: for composite images write only **necessary content items + free-play items**, do not lock the cell count (record historical accidents in the "layout conventions" section of the project record); or, for a single panorama, the foreground/midground/background depth layers.
7. **Exclusions**: list per this order's needs (no people/no creatures/no text/no environment/no grid lines...).
8. **Negative words**: at minimum include the general baseline — distorted proportions, subject too small, grid collage, text watermark; project-specific negative words (pitfalls hit before) come from the "negative words" section of the project record `.image-generation/profile.md` (example in `references/profile.example.md`).

## Two prompt disciplines (already tested)

1. **When there is a reference image, write no shape description in the prompt.**
   Shape / structure / material etc. are provided by the reference image; the body text **must not** contain textual descriptions of them.
   The body text writes only information the reference image cannot give: state, action, orientation, background, art style, exclusions.
   Reason: item-by-item textual description competes with the reference image; the model may repaint an "average body that matches the description", causing subject drift.
   (**Not** writing a line like "for shape follow image 1, do not describe separately" — that line is still redundant narration; simply do not write it.)

2. **The prompt contains only the image description needed for generation; write nothing else.**
   "Generate a...", "make it a...", "based on image X", "this task is..." and other **narrations of the generation behavior or process**
   have no effect on the model's output and must not be written into the prompt — they belong to the explanation in the conversation/document.
   Refer to reference images directly as "image 1 / image 2"; no need for a preamble like "based on image 1".

## Settled design decisions — verification sources

Content settled in discussion must go into the prompt; verify it against the table below:

> Concretely, the path follows the "settled-decision verification sources" section of the project record `.image-generation/profile.md` (example in `references/profile.example.md`).

| Decision type | Where to check |
|---|---|
| Aspect ratio / size | Your project's size / aspect-ratio spec document |
| Shape features / anchor card | Your project's character / setting material |
| Structure and opening mechanism | Your project's setting text (grounded); what the user decided in conversation (must also check whether the setting has been synced) |
| Front/back features, character/scene domain division | Conversation decision records; your project's asset spec |
| Reference-image division | Which reference image the user assigned to govern what (appearance/structure/aspect ratio) |

**Grounded vs inferred**: details that are not in the project text and are filled in by reasoning (e.g. the form of a meshing mechanism) are marked as "inferred item" in the prompt, not passed off as setting.

## Pre-output self-check

- Is the prompt **self-contained**: viewed alone apart from the conversation, does it still contain all settled constraints?
- With a reference image, does the text conflict with the reference image's content? → delete the conflicting description (shape is left to the reference image).
- Are all eight sections present, and do the negative words include pitfalls this asset has hit?
- With a reference image, does the body text **retain a shape-description sentence**? → delete.
- Is any non-image description mixed in, such as "generate a.../based on image X"? → delete.
- Ask of each sentence: does this describe "**what it looks like in the image**"? If not → delete.

## Official prompting iron rules (source: the `image-gen/references/prompting.md` of the heyroute official skill repo, not a file in this directory)

- **Structural order**: scene/background → subject → details (material/light/color scheme) → constraints (must keep / must not appear).
- **Image editing must explicitly list invariants**: "change only X; keep Y, Z unchanged", **repeated on every iteration round**, to prevent drift; **change only one spot at a time**.
- If the user's description is already specific, just tidy it and do not add drama; only when it is very vague, fill in composition/lighting/purpose, and do not add elements the user did not imply.
- State the purpose; for photorealistic photos use camera language (focal length / shot size / light).
- Give in-image text verbatim in quotes and specify its position; lots of text is bound to be messy, so leave it out when possible.
- `n` is always 1: multiple assets = multiple calls, do not expect a full set in one go.
- Do not generate icon/wireframe/vector assets; writing SVG/CSS directly is more controllable.
