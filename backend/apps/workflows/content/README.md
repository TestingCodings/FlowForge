# App content

Demo and client app content as YAML, loaded by `manage.py load_app <name>`.

```
content/
└── demo/
    ├── app.yaml            identity + the file list
    ├── *.yaml              one workflow each, in the YAML DSL
    └── instances.yaml      demo instances and relationships
```

## Why YAML rather than Python

Each workflow file is the same DSL the in-app YAML editor uses. It compiles
through `parse_dsl` into exactly the bundle `portability.export_workflow`
produces, then imports through `import_workflow` — **the same path a client's
delivered app takes**. Seeding and delivery therefore cannot drift, and an
import bug shows up in our own demo before a client sees it.

It also means content is diffable, commentable, and editable by someone other
than whoever wrote it.

## Rules to keep

- **Instances are advanced by firing transitions** (`advance:`), never by
  writing `current_state`. That is what gives them real timelines and audit
  trails, which is one of the strongest things the demo shows. `load_app`
  fails loudly if a rule blocks a seeded advance, because content and rules
  disagreeing should not produce a quietly-wrong demo.
- **`ref:` is a local handle** for wiring up parents and relationships. It's
  stored in metadata so it survives the load.
- **Order matters** in `app.yaml`'s `workflows:` list — a file may reference
  workflows loaded before it (containment allow-lists, relationship targets).

## Commands

```bash
python manage.py load_app demo            # refuses if already loaded
python manage.py load_app demo --reset    # replace, deleting its instances
python manage.py load_app demo --skip-identity   # leave workspace branding alone
```
