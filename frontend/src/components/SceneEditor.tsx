import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { Scene, SceneConfig, SceneSprite, Workflow } from "../types/api";
import Hint from "./Hint";
import SceneAssetField from "./scene/SceneAssetField";

interface Props {
  workflow: Workflow;
}

interface SpriteFieldErrors {
  row?: string;
  asset?: string;
  position?: string;
}

interface StateSceneErrors {
  scene?: string;
  background?: string;
  speaker?: string;
  dialogue?: string;
  music?: string;
  sprites?: string;
  spriteErrors?: Record<number, SpriteFieldErrors>;
}

interface SceneEditorErrors {
  global?: string;
  states: Record<string, StateSceneErrors>;
}

function cloneSceneConfig(config: SceneConfig): SceneConfig {
  const next: SceneConfig = {};
  for (const [stateName, scene] of Object.entries(config ?? {})) {
    next[stateName] = {
      ...scene,
      sprites: scene.sprites?.map((sprite) => ({ ...sprite })),
    };
  }
  return next;
}

function serialiseSceneConfig(config: SceneConfig): SceneConfig {
  const next: SceneConfig = {};
  for (const [stateName, scene] of Object.entries(config ?? {})) {
    const serialised: Scene = {};
    if (scene.background !== undefined && scene.background !== "") serialised.background = scene.background;
    if (scene.speaker !== undefined && scene.speaker !== "") serialised.speaker = scene.speaker;
    if (scene.dialogue !== undefined && scene.dialogue !== "") serialised.dialogue = scene.dialogue;
    if (scene.music !== undefined && scene.music !== "") serialised.music = scene.music;

    const sprites = (scene.sprites ?? []).map((sprite) => {
        const nextSprite: SceneSprite = { asset: sprite.asset };
        if (sprite.position) nextSprite.position = sprite.position;
        return nextSprite;
      });
    if (sprites.length) serialised.sprites = sprites;

    if (Object.keys(serialised).length > 0) next[stateName] = serialised;
  }
  return next;
}

function hasContent(scene?: Scene): boolean {
  if (!scene) return false;
  return Boolean(
    scene.background ||
    scene.speaker ||
    scene.dialogue ||
    scene.music ||
    (scene.sprites?.length ?? 0) > 0
  );
}

function emptyErrors(): SceneEditorErrors {
  return { states: {} };
}

function parseSceneError(message: string | null | undefined): SceneEditorErrors {
  if (!message) return emptyErrors();

  const stateField = message.match(/^ui_schema\.scene_config\['(.+)'\]\.(background|speaker|dialogue|music) must be a string\.$/);
  if (stateField) {
    const [, stateName, field] = stateField;
    return { states: { [stateName]: { [field]: message } } };
  }

  const sceneObject = message.match(/^ui_schema\.scene_config\['(.+)'\] must be an object\.$/);
  if (sceneObject) {
    const [, stateName] = sceneObject;
    return { states: { [stateName]: { scene: message } } };
  }

  const spriteList = message.match(/^ui_schema\.scene_config\['(.+)'\]\.sprites must be a list\.$/);
  if (spriteList) {
    const [, stateName] = spriteList;
    return { states: { [stateName]: { sprites: message } } };
  }

  const spriteObject = message.match(/^ui_schema\.scene_config\['(.+)'\]\.sprites\[(\d+)\] must be an object\.$/);
  if (spriteObject) {
    const [, stateName, index] = spriteObject;
    return {
      states: {
        [stateName]: {
          spriteErrors: { [Number(index)]: { row: message } },
        },
      },
    };
  }

  const spriteAsset = message.match(/^ui_schema\.scene_config\['(.+)'\]\.sprites\[(\d+)\] requires an 'asset'\.$/);
  if (spriteAsset) {
    const [, stateName, index] = spriteAsset;
    return {
      states: {
        [stateName]: {
          spriteErrors: { [Number(index)]: { asset: message } },
        },
      },
    };
  }

  const spritePosition = message.match(/^ui_schema\.scene_config\['(.+)'\]\.sprites\[(\d+)\]\.position must be one of: .+\.$/);
  if (spritePosition) {
    const [, stateName, index] = spritePosition;
    return {
      states: {
        [stateName]: {
          spriteErrors: { [Number(index)]: { position: message } },
        },
      },
    };
  }

  return message === "ui_schema.scene_config must be an object keyed by state name."
    ? { global: message, states: {} }
    : { global: message, states: {} };
}

export default function SceneEditor({ workflow }: Props) {
  const qc = useQueryClient();
  const workflowIdRef = useRef(workflow.id);
  const [sceneConfig, setSceneConfig] = useState<SceneConfig>({});
  const [saved, setSaved] = useState(false);
  const [errors, setErrors] = useState<SceneEditorErrors>(emptyErrors());

  useEffect(() => {
    setSceneConfig(cloneSceneConfig(workflow.ui_schema?.scene_config ?? {}));
    setErrors(emptyErrors());
    if (workflowIdRef.current !== workflow.id) setSaved(false);
    workflowIdRef.current = workflow.id;
  }, [workflow]);

  const states = useMemo(
    () => [...(workflow.states ?? [])].sort((a, b) => a.position_order - b.position_order),
    [workflow.states],
  );

  const clearErrors = () => setErrors(emptyErrors());

  const updateScene = (stateName: string, updater: (scene: Scene) => Scene) => {
    clearErrors();
    setSaved(false);
    setSceneConfig((current) => {
      const scene = current[stateName] ?? {};
      return { ...current, [stateName]: updater({ ...scene, sprites: scene.sprites?.map((sprite) => ({ ...sprite })) }) };
    });
  };

  const save = useMutation({
    mutationFn: async () => {
      const nextSceneConfig = serialiseSceneConfig(sceneConfig);
      return (
        await apiClient.patch(`/workflows/${workflow.id}/ui-schema/`, {
          ui_schema: {
            ...(workflow.ui_schema ?? {}),
            scene_config: nextSceneConfig,
          },
        })
      ).data as Workflow;
    },
    onSuccess: (nextWorkflow) => {
      setSceneConfig(cloneSceneConfig(nextWorkflow.ui_schema?.scene_config ?? {}));
      setErrors(emptyErrors());
      setSaved(true);
      qc.invalidateQueries({ queryKey: ["workflow", workflow.id] });
      setTimeout(() => setSaved(false), 3000);
    },
    onError: (err: any) => {
      const message = err?.response?.data?.detail ??
        (typeof err?.response?.data === "string" ? err.response.data : null) ??
        "Failed to save scenes.";
      setErrors(parseSceneError(message));
    },
  });

  return (
    <div className="card mt-4">
      <div className="card-header">
        <div className="flex items-center gap-3">
          <h3>Scenes <Hint tip="Configure how each workflow state appears in the scene shell: background, characters, speaker, dialogue and music." /></h3>
          <span className="badge badge-active">{Object.keys(serialiseSceneConfig(sceneConfig)).length} configured</span>
        </div>
        <button className="btn-primary btn-sm" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save scenes"}
        </button>
      </div>

      <p className="text-sm text-muted" style={{ marginBottom: 14 }}>
        Scene config is stored in <code>ui_schema.scene_config</code>, keyed by the workflow state name.
        Dialogue supports <code>{"{{metadata.key}}"}</code> and <code>{"{{instance.reference_number}}"}</code>.
      </p>

      {saved && <div className="alert alert-success mb-2">Scenes saved.</div>}
      {errors.global && <div className="alert alert-error mb-2">{errors.global}</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {states.map((state) => {
          const scene = sceneConfig[state.name] ?? {};
          const stateErrors = errors.states[state.name] ?? {};
          return (
            <div
              key={state.id}
              data-scene-state={state.name}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 12,
                padding: 16,
                background: "var(--bg-elevated)",
              }}
            >
              <div className="flex items-center gap-3 mb-3" style={{ justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontWeight: 700 }}>{state.display_name || state.name}</div>
                  <div className="text-xs text-muted" style={{ fontFamily: "monospace", marginTop: 2 }}>
                    Config key: {state.name}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {hasContent(scene)
                    ? <span className="badge badge-active">Configured</span>
                    : <span className="badge badge-inactive">Empty</span>}
                  <button
                    type="button"
                    className="btn-ghost btn-sm"
                    disabled={!hasContent(scene)}
                    onClick={() => {
                      clearErrors();
                      setSaved(false);
                      setSceneConfig((current) => {
                        const next = { ...current };
                        delete next[state.name];
                        return next;
                      });
                    }}
                  >
                    Clear scene
                  </button>
                </div>
              </div>

              {stateErrors.scene && <div className="alert alert-error mb-3">{stateErrors.scene}</div>}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Background</label>
                  <SceneAssetField
                    workflowId={workflow.id}
                    value={scene.background}
                    onChange={(value) => updateScene(state.name, (current) => ({ ...current, background: value }))}
                    accept="image/*"
                    error={stateErrors.background}
                  />
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Music</label>
                  <SceneAssetField
                    workflowId={workflow.id}
                    value={scene.music}
                    onChange={(value) => updateScene(state.name, (current) => ({ ...current, music: value }))}
                    accept="audio/*"
                    error={stateErrors.music}
                  />
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Speaker</label>
                  <input
                    data-scene-field="speaker"
                    value={scene.speaker ?? ""}
                    onChange={(e) => updateScene(state.name, (current) => ({ ...current, speaker: e.target.value }))}
                    placeholder="e.g. Narrator"
                  />
                  {stateErrors.speaker && <div className="text-xs" style={{ color: "var(--danger)", marginTop: 4 }}>{stateErrors.speaker}</div>}
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Dialogue</label>
                  <textarea
                    data-scene-field="dialogue"
                    value={scene.dialogue ?? ""}
                    onChange={(e) => updateScene(state.name, (current) => ({ ...current, dialogue: e.target.value }))}
                    placeholder="Write the scene text shown to the player."
                    rows={5}
                    style={{ resize: "vertical" }}
                  />
                  {stateErrors.dialogue && <div className="text-xs" style={{ color: "var(--danger)", marginTop: 4 }}>{stateErrors.dialogue}</div>}
                </div>
              </div>

              <div style={{ marginTop: 14 }}>
                <div className="flex items-center gap-2 mb-2">
                  <div style={{ fontSize: "0.78rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--text-secondary)" }}>
                    Sprites
                  </div>
                  {(scene.sprites ?? []).length > 0 && (
                    <span className="badge badge-inactive">{scene.sprites?.length} placed</span>
                  )}
                </div>
                <p className="text-xs text-muted" style={{ marginBottom: 10 }}>
                  Positions must use British spelling: <code>left</code>, <code>centre</code>, <code>right</code>.
                </p>
                {stateErrors.sprites && <div className="alert alert-error mb-2">{stateErrors.sprites}</div>}

                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {(scene.sprites ?? []).map((sprite, index) => {
                    const spriteErrors = stateErrors.spriteErrors?.[index] ?? {};
                    return (
                      <div
                        key={`${state.name}-sprite-${index}`}
                        data-scene-sprite={index}
                        style={{
                          border: "1px solid var(--border)",
                          borderRadius: 10,
                          padding: 12,
                          background: "var(--bg-base)",
                        }}
                      >
                        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 140px auto", gap: 10, alignItems: "start" }}>
                          <div className="form-group" style={{ marginBottom: 0 }}>
                            <label>Asset</label>
                            <SceneAssetField
                              workflowId={workflow.id}
                              value={sprite.asset}
                              onChange={(value) => updateScene(state.name, (current) => ({
                                ...current,
                                sprites: (current.sprites ?? []).map((row, i) => i === index ? { ...row, asset: value } : row),
                              }))}
                              accept="image/*"
                              error={spriteErrors.asset}
                            />
                          </div>

                          <div className="form-group" style={{ marginBottom: 0 }}>
                            <label>Position</label>
                            <select
                              value={sprite.position ?? "centre"}
                              onChange={(e) => updateScene(state.name, (current) => ({
                                ...current,
                                sprites: (current.sprites ?? []).map((row, i) => (
                                  i === index ? { ...row, position: e.target.value as SceneSprite["position"] } : row
                                )),
                              }))}
                            >
                              <option value="left">left</option>
                              <option value="centre">centre</option>
                              <option value="right">right</option>
                            </select>
                            {spriteErrors.position && <div className="text-xs" style={{ color: "var(--danger)", marginTop: 4 }}>{spriteErrors.position}</div>}
                          </div>

                          <button
                            type="button"
                            className="btn-ghost btn-sm"
                            style={{ color: "var(--danger)", marginTop: 24, paddingInline: 10 }}
                            onClick={() => updateScene(state.name, (current) => ({
                              ...current,
                              sprites: (current.sprites ?? []).filter((_, i) => i !== index),
                            }))}
                          >
                            Remove
                          </button>
                        </div>
                        {spriteErrors.row && <div className="text-xs" style={{ color: "var(--danger)", marginTop: 8 }}>{spriteErrors.row}</div>}
                      </div>
                    );
                  })}
                </div>

                <button
                  type="button"
                  className="btn-ghost btn-sm"
                  style={{ marginTop: 10, width: "100%", borderStyle: "dashed" }}
                  onClick={() => updateScene(state.name, (current) => ({
                    ...current,
                    sprites: [...(current.sprites ?? []), { asset: "", position: "centre" }],
                  }))}
                >
                  + Add sprite
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
