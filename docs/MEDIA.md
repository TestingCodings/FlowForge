# Media & Attachments — Design (future addition)

Uploading and embedding images (and other files), and the larger ambition it
unlocks: **visual-novel / narrative-game authoring** inside FlowForge, to a
level comparable with Ren'Py or a Unity 2D scene flow.

Status: **Part 1 (backend) implemented** (WS-A). Part 2 (visual-novel shell, WS-I) is pending WS-B (frontend attachments panel).

---

## Part 1 — File & image uploads

Today `metadata_json` is text-only; there is no way to attach a device photo,
an evidence scan, a claim document, or — for the game direction — a background
or character sprite. Two capabilities:

### 1a. Embedding (show an image already on the web) — small
Mostly works already: `logo_url` embeds the workspace logo. Extend to:
- an `image` **form-field type** and a `metadata.<key>` that holds a URL;
- render with `referrerpolicy="no-referrer"` and `loading="lazy"`; block
  mixed content; optionally proxy through the backend against an allow-list to
  avoid leaking viewer IPs to arbitrary hosts.

### 1b. Uploading (store a file FlowForge owns) — ~1 week

**Model** (`apps/media/models.py`):
```python
class MediaAsset(models.Model):
    id            = UUIDField(pk)
    workflow_instance = FK(WorkflowInstance, null=True, related_name="assets")
    workflow_definition = FK(WorkflowDefinition, null=True)   # for reusable game assets
    file          = FileField(upload_to=...)      # or S3 key
    original_name = CharField
    content_type  = CharField
    size_bytes    = PositiveBigInteger
    kind          = CharField(choices=["image","document","audio","other"])
    uploaded_by   = FK(User, SET_NULL)
    created_at    = DateTimeField
```

**Storage.** Local dev: Django `FileField` on disk (no Docker needed, matches
the SQLite dev story). Production/demo: **S3-compatible object storage via
`django-storages`** — Cloudflare R2 is the natural pick (cheap, no egress
fees, pairs with the cortexa.solutions hosting). One `DEFAULT_FILE_STORAGE`
swap, no model change.

**API.**
- `POST /api/media/` `multipart/form-data` (file + optional instance) → asset
  metadata + a URL. participant+ to upload.
- `GET /api/media/<id>/` → the file, access-checked (never a public bucket by
  default; signed URLs or a Django view that authorises then streams/redirects).
- `DELETE /api/media/<id>/` (uploader or designer+).

**Security (the weight of this feature):**
- **Type + size allow-list** enforced server-side (magic-byte sniff, not just
  the client-sent content-type); configurable max size.
- **Never trust the filename** — store under a generated key; sanitise
  `original_name` for display only.
- **Auth on download** — assets default to private; a public flag is opt-in.
- **Image re-encoding** — strip EXIF and re-encode uploaded images (Pillow) to
  defuse polyglot/embedded-payload files.
- **Antivirus** hook point for production (ClamAV or a scanning service) via an
  after-upload action hook — the hooks system already exists.

**Frontend.** An `image`/`file` form-field type (drag-drop), an Attachments
panel on the instance detail page (an `instance_view` panel), and image
thumbnails inline in the metadata display.

---

## Part 2 — Visual-novel / narrative-game authoring

The ambition: author branching, choice-driven games — Ren'Py-style visual
novels, and beyond that simple Unity-2D-style scene flows — **without leaving
FlowForge's model**. The striking part is how little new machinery this needs,
because the meta-model already maps onto a narrative engine:

| Game concept | FlowForge primitive (already built) |
|---|---|
| Scene | **State** |
| Choice / branch | **Transition** (multiple out of a state) |
| Conditional branch ("if flag set") | **Rule** on a transition (block/allow) |
| Variables / flags / inventory | **metadata_json** |
| Derived stats (score, affection, HP) | **Computed fields** |
| Player's save file / playthrough | **Instance** (each is one player's run) |
| Multiple concurrent story threads | **Parallel states** (planned) |
| Dialogue, background, sprite, music | **metadata + Media assets** (Part 1) |
| External event advances the story | **Inbound trigger** |
| Side effects (award achievement, call API) | **Action hooks** |

So a "game" is a workflow; a "playthrough" is an instance; the state graph
*is* the story graph. What's missing is **presentation and authoring for the
narrative case**:

### What Part 2 needs on top of Part 1

1. **A "scene" shell** (`shell: "scene"`) — a full-viewport player, not a
   dashboard view. It renders the current state's:
   - `background` image (a media asset referenced in state config),
   - character `sprites` with positions (left/centre/right),
   - a `dialogue` box (speaker + text, from state config with `{{metadata.*}}`
     interpolation — the templating from action hooks generalises here),
   - the available transitions as **choice buttons**, hiding ones a rule
     blocks (so choices appear only when their conditions are met).
   Firing a transition = making a choice; the engine already enforces rules,
   so "you need the key to open the door" is just a metadata rule.

2. **Scene config on states** — extend `ui_schema` (or a `scene_config` on
   State) with `{background, sprites:[{asset, position}], dialogue, music}`.
   Validated like the other ui_schema blocks.

3. **A scene authoring surface** — the visual builder already draws the state
   graph (= story map). Add a per-state scene editor (pick background/sprites,
   write dialogue) — the builder becomes a visual novel editor. The YAML DSL
   already expresses states+transitions+rules, so a game is *also* authorable
   as text and diffable.

4. **Save/resume** — an instance already *is* a save file (metadata =
   variables, current_state = position). "Continue" = reopen the instance;
   "New game" = new instance. No new mechanism.

### How far this realistically goes

- **Comfortably in reach (Ren'Py-class):** branching dialogue, choices gated
  by flags/inventory, variables and derived stats, multiple endings, character
  routes, save/resume, backgrounds/sprites/music. This is a genuine visual
  novel engine — mostly the scene shell + media + scene config.
- **A stretch (needs parallel states):** concurrent story threads, time
  systems, simultaneous stat tracking across arcs.
- **Out of scope (not what FlowForge is):** real-time action, physics, free
  movement, frame-by-frame animation — anything not expressible as
  discrete states and choices. That's where the Unity comparison ends: 2D
  *scene-flow / choice* games map on well; *action* games do not.

### Suggested build order for the game direction
1. Part 1 uploads (needed for any visual asset).
2. `scene` shell + `scene_config` (turns a workflow into a playable VN).
3. Scene authoring in the builder.
4. Parallel states (only if concurrent threads are wanted).

A demo "workflow" — a short branching story with two endings gated by an
inventory flag — would prove the whole stack end to end and make a
memorable portfolio piece: *"this workflow engine is also a visual-novel
engine, because a process and a story are the same shape."*
